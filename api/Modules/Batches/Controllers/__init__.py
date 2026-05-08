"""Batches module — Controllers (FastAPI router).

Mounts at `/api/v2/batches/*` (the parent router in
`api/main.py` adds `/batches`; the FastAPI app's
`root_path="/api/v2"` carries the version prefix).

Read-side only:

  GET /batches → all ACH batches for the JWT principal's store,
                  sorted, with precomputed transfers_total +
                  variance + transfer_count.

Write-side (create / edit / link transfers) stays on the
legacy Flask `/batches/new`, `/batches/<id>/edit`,
`/batches/<id>/transfers` routes until subsequent PRs
migrate them.
"""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from sqlalchemy.orm import Session

from api.Core.Database import get_db
from api.Modules.Auth.Controllers import get_principal
from api.Modules.Batches.Models import Transfer
from api.Modules.Batches.Repositories import (
    sum_transfer_totals_for_batch_refs,
    transfer_count_by_batch_ref,
)
from api.Modules.Batches.Requests import (
    BatchLinkedTransferRow,
    BatchListResponse,
    BatchResponse,
    BatchRow,
    BatchTransfersResponse,
    BatchWriteRequest,
)
from api.Modules.Batches.Services import (
    BatchNotFoundError,
    BatchValidationError,
    BatchWriteInput,
    create_batch,
    find_batch,
    list_store_batches,
    update_batch,
)
from api.Modules.Batches.Services.batches import BatchSummary


router = APIRouter()


def _row(s: BatchSummary) -> BatchRow:
    b = s.batch
    return BatchRow(
        id=b.id,
        ach_date=b.ach_date.isoformat() if b.ach_date else "",
        company=b.company or "",
        batch_ref=b.batch_ref or "",
        ach_amount=float(b.ach_amount or 0),
        status=b.status or "Pending",
        reconciled=bool(b.reconciled),
        transfer_dates=b.transfer_dates or "",
        notes=b.notes or "",
        transfers_total=s.transfers_total,
        variance=s.variance,
        transfer_count=s.transfer_count,
    )


@router.get("", response_model=BatchListResponse)
def list_route(
    sort: str = Query(
        "",
        description=(
            "Column slug to sort by (ach_date, company, batch_ref, "
            "ach_amount, status). Empty falls back to "
            "ach_date desc."
        ),
    ),
    direction: str = Query(
        "desc", pattern="^(asc|desc)$",
    ),
    db: Session = Depends(get_db),
    claims: dict = Depends(get_principal),
) -> BatchListResponse:
    """List ACH batches in the JWT principal's store. Superadmin
    JWTs (no store_id claim) → 403 — this endpoint is store-
    scoped."""
    store_id = claims.get("store_id")
    if store_id is None:
        raise HTTPException(
            status_code=403,
            detail=(
                "JWT does not carry a store scope. Sign in as a "
                "store admin or owner to view batches."
            ),
        )
    rows = list_store_batches(
        db, int(store_id), sort=sort, direction=direction,
    )
    return BatchListResponse(rows=[_row(r) for r in rows])


def _require_admin_scope(claims: dict) -> int:
    """Both store_id (write is store-scoped) AND admin role
    (cashiers can't manage batches in the legacy admin_required
    path)."""
    sid = claims.get("store_id")
    if sid is None:
        raise HTTPException(
            status_code=403,
            detail="JWT does not carry a store scope.",
        )
    if claims.get("role") not in ("admin", "owner", "superadmin"):
        raise HTTPException(
            status_code=403,
            detail="Only store admins can manage ACH batches.",
        )
    return int(sid)


def _parse_payload(body: BatchWriteRequest) -> BatchWriteInput:
    try:
        ach_date = datetime.strptime(body.ach_date, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(
            status_code=422,
            detail={
                "field": "ach_date",
                "message": "Date must be YYYY-MM-DD.",
            },
        )
    return BatchWriteInput(
        ach_date=ach_date,
        company=body.company,
        batch_ref=body.batch_ref,
        ach_amount=float(body.ach_amount or 0),
        transfer_dates=body.transfer_dates,
        status=body.status or "Pending",
        reconciled=bool(body.reconciled),
        notes=body.notes,
    )


def _row_with_totals(
    db: Session, store_id: int, batch,
) -> BatchRow:
    """Build a BatchRow with the live transfer totals attached.
    Done as one bulk query rather than the legacy per-row
    ACHBatch.transfers_total property (which N+1's)."""
    refs = [batch.batch_ref] if batch.batch_ref else []
    totals = sum_transfer_totals_for_batch_refs(db, store_id, refs)
    counts = transfer_count_by_batch_ref(db, store_id, refs)
    transfers_total = totals.get(batch.batch_ref, 0.0)
    return BatchRow(
        id=batch.id,
        ach_date=batch.ach_date.isoformat() if batch.ach_date else "",
        company=batch.company or "",
        batch_ref=batch.batch_ref or "",
        ach_amount=float(batch.ach_amount or 0),
        status=batch.status or "Pending",
        reconciled=bool(batch.reconciled),
        transfer_dates=batch.transfer_dates or "",
        notes=batch.notes or "",
        transfers_total=transfers_total,
        variance=round(float(batch.ach_amount or 0) - transfers_total, 2),
        transfer_count=counts.get(batch.batch_ref, 0),
    )


@router.get("/{batch_id}", response_model=BatchResponse)
def get_batch_route(
    batch_id: int = Path(..., ge=1),
    db: Session = Depends(get_db),
    claims: dict = Depends(get_principal),
) -> BatchResponse:
    """Single-batch detail. Cross-tenant lookups → 404."""
    sid = claims.get("store_id")
    if sid is None:
        raise HTTPException(
            status_code=403,
            detail="JWT does not carry a store scope.",
        )
    row = find_batch(db, int(sid), batch_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Batch not found")
    return BatchResponse(batch=_row_with_totals(db, int(sid), row))


@router.post("", response_model=BatchResponse, status_code=201)
def create_batch_route(
    body: BatchWriteRequest,
    db: Session = Depends(get_db),
    claims: dict = Depends(get_principal),
) -> BatchResponse:
    """Create an ACH batch. Admin role + store scope required."""
    sid = _require_admin_scope(claims)
    payload = _parse_payload(body)
    try:
        row = create_batch(db, sid, payload)
    except BatchValidationError as exc:
        raise HTTPException(
            status_code=422,
            detail={"field": "batch_ref", "message": str(exc)},
        )
    db.commit()
    return BatchResponse(batch=_row_with_totals(db, sid, row))


@router.put("/{batch_id}", response_model=BatchResponse)
def update_batch_route(
    batch_id: int = Path(..., ge=1),
    body: BatchWriteRequest = ...,
    db: Session = Depends(get_db),
    claims: dict = Depends(get_principal),
) -> BatchResponse:
    """Update an ACH batch. Admin role + store scope required.
    Cross-tenant updates → 404."""
    sid = _require_admin_scope(claims)
    payload = _parse_payload(body)
    try:
        row = update_batch(
            db, batch_id=batch_id, store_id=sid, payload=payload,
        )
    except BatchNotFoundError:
        raise HTTPException(status_code=404, detail="Batch not found")
    except BatchValidationError as exc:
        raise HTTPException(
            status_code=422,
            detail={"field": "batch_ref", "message": str(exc)},
        )
    db.commit()
    return BatchResponse(batch=_row_with_totals(db, sid, row))


@router.get(
    "/{batch_id}/transfers",
    response_model=BatchTransfersResponse,
)
def batch_transfers_route(
    batch_id: int = Path(..., ge=1),
    db: Session = Depends(get_db),
    claims: dict = Depends(get_principal),
) -> BatchTransfersResponse:
    """List the transfers linked to one ACH batch by
    `batch_id == batch_ref`. Mirrors the legacy
    /batches/<id>/transfers Jinja page."""
    sid = claims.get("store_id")
    if sid is None:
        raise HTTPException(
            status_code=403,
            detail="JWT does not carry a store scope.",
        )
    batch = find_batch(db, int(sid), batch_id)
    if batch is None:
        raise HTTPException(status_code=404, detail="Batch not found")
    rows = (
        db.query(Transfer)
          .filter_by(store_id=int(sid), batch_id=batch.batch_ref)
          .order_by(Transfer.send_date.asc(), Transfer.id.asc())
          .all()
    )
    return BatchTransfersResponse(
        transfers=[
            BatchLinkedTransferRow(
                id=t.id,
                send_date=t.send_date.isoformat() if t.send_date else "",
                company=t.company or "",
                sender_name=t.sender_name or "",
                recipient_name=t.recipient_name or "",
                country=t.country or "",
                confirm_number=t.confirm_number or "",
                send_amount=float(t.send_amount or 0),
                fee=float(t.fee or 0),
                federal_tax=float(t.federal_tax or 0),
                total_collected=float(t.total_collected),
                status=t.status or "Sent",
            )
            for t in rows
        ],
    )
