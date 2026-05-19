"""Batches module — Controllers (FastAPI router).

Mounts at ``/api/v2/batches/*``. Lists ACH batches for the
caller's store with precomputed transfers_total + variance, plus
the per-batch create / edit / link-transfers endpoints the SPA
batches page uses.
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
from typing import Any


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
    claims: dict[str, Any] = Depends(get_principal),
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


def _require_admin_scope(claims: dict[str, Any]) -> int:
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


def _audit_batch(db, claims, action, batch, *, summary):
    """Operator-audit helper. Mirrors the legacy
    `record_op_audit('create'/'update', 'batch', ...)` calls that
    the Flask form-POST handlers used to make. With the SPA POSTing
    here directly, the audit row needs to land on this side or it
    silently disappears from the operator audit log.

    Actor identity comes from the JWT claims (no DB roundtrip);
    `record_operator_action` is the per-store audit Service that
    backs both surfaces.
    """
    from api.Modules.Audit.Services import record_operator_action
    sid = int(claims["store_id"])
    record_operator_action(
        db,
        store_id=sid,
        user_id=int(claims["sub"]),
        user_name=claims.get("name") or claims.get("username") or "",
        user_role=claims.get("role") or "",
        target_type="batch",
        target_id=batch.id,
        target_label=f"{batch.company or ''} {batch.batch_ref or ''}".strip(),
        action=action,
        summary=summary,
    )


def _diff_summary(before: dict[str, Any], after: dict[str, Any]) -> str:
    """Format a `field old→new; field old→new` summary string for
    the operator audit log, matching the legacy /batches/<id>/edit
    handler's output. Only fields that actually changed appear."""
    diffs = []
    if before["ach_amount"] != after["ach_amount"]:
        diffs.append(
            f"amount {before['ach_amount']:,.2f}→{after['ach_amount']:,.2f}"
        )
    if before["status"] != after["status"]:
        diffs.append(f"status {before['status']}→{after['status']}")
    if before["reconciled"] != after["reconciled"]:
        diffs.append(
            f"reconciled {before['reconciled']}→{after['reconciled']}"
        )
    return "; ".join(diffs) if diffs else "no field changes"


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
    claims: dict[str, Any] = Depends(get_principal),
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
    claims: dict[str, Any] = Depends(get_principal),
) -> BatchResponse:
    """Create an ACH batch. Admin role + store scope required.

    Writes an `OperatorAuditLog` row (`action='create',
    target_type='batch'`) so the audit trail mirrors what the legacy
    /batches/new Flask handler used to record. Without this, SPA
    creates would silently bypass the audit log."""
    sid = _require_admin_scope(claims)
    payload = _parse_payload(body)
    try:
        row = create_batch(db, sid, payload)
    except BatchValidationError as exc:
        raise HTTPException(
            status_code=422,
            detail={"field": "batch_ref", "message": str(exc)},
        )
    summary = (
        f"ach_amount=${float(row.ach_amount or 0):,.2f} "
        f"date={row.ach_date.isoformat() if row.ach_date else ''} "
        f"status={row.status or ''}"
    )
    _audit_batch(db, claims, "create", row, summary=summary)
    db.commit()
    return BatchResponse(batch=_row_with_totals(db, sid, row))


@router.put("/{batch_id}", response_model=BatchResponse)
def update_batch_route(
    batch_id: int = Path(..., ge=1),
    body: BatchWriteRequest = ...,
    db: Session = Depends(get_db),
    claims: dict[str, Any] = Depends(get_principal),
) -> BatchResponse:
    """Update an ACH batch. Admin role + store scope required.
    Cross-tenant updates → 404. Writes an `OperatorAuditLog` row
    summarising before→after diffs on the fields the legacy form
    tracked (amount, status, reconciled) so the operator-side audit
    trail stays consistent with the SPA cutover."""
    sid = _require_admin_scope(claims)
    payload = _parse_payload(body)
    # Snapshot the fields that the legacy edit handler diffed before
    # we mutate them. The Service mutates in-place, so we have to
    # capture this here in the Controller.
    existing = find_batch(db, sid, batch_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Batch not found")
    before = {
        "ach_amount": float(existing.ach_amount or 0),
        "status": existing.status or "",
        "reconciled": bool(existing.reconciled),
    }
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
    after = {
        "ach_amount": float(row.ach_amount or 0),
        "status": row.status or "",
        "reconciled": bool(row.reconciled),
    }
    _audit_batch(
        db, claims, "update", row, summary=_diff_summary(before, after),
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
    claims: dict[str, Any] = Depends(get_principal),
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
