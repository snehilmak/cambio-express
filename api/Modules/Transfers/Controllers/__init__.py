"""Transfers module — Controllers (FastAPI router).

Mounts at `/api/v2/transfers/*` (the parent router in `api/main.py`
adds `/transfers`; the FastAPI app's `root_path="/api/v2"` carries
the version prefix).

PR 12 ships the read-side only:

  GET /transfers → paginated list with the same filter shape as the
                   legacy /transfers route's query string.

PR 13 will flip the legacy /transfers route to call the same Service
this Controller does. PR 14+ will add the write-side
(POST /transfers, PUT /transfers/{id}) once the create/edit business
logic moves into Services.

Auth gating intentionally NOT here yet — auth migration is module 5
of 6 in the ADR.

Layer rules:
    Controller → Service     ✓
    Controller → Repository  ✗
    Controller → DB session  ✓ (only via Depends(get_db))
"""
from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from sqlalchemy.orm import Session

from api.Core.Database import get_db
from api.Modules.Transfers.Repositories import (
    TransferFilters,
    get_by_id_in_stores,
)
from api.Modules.Transfers.Requests import (
    TransferListResponse,
    TransferResponse,
    TransferRow,
)
from api.Modules.Transfers.Services import list_transfers


router = APIRouter()


def _parse_store_ids(store_ids: str) -> list[int]:
    """Reuse the same comma-separated → list[int] parser shape as the
    Reports controllers. Mirrors how the legacy Flask routes handle
    multi-store admin/owner views."""
    try:
        ids = [int(s.strip()) for s in store_ids.split(",") if s.strip()]
    except ValueError as e:
        raise HTTPException(
            status_code=422,
            detail=f"store_ids must be comma-separated integers: {e}",
        )
    if not ids:
        raise HTTPException(
            status_code=422, detail="store_ids must include at least one ID",
        )
    return ids


def _to_row(t) -> TransferRow:
    return TransferRow(
        id=t.id,
        send_date=t.send_date.isoformat() if t.send_date else "",
        company=t.company or "",
        service_type=t.service_type or "Money Transfer",
        sender_name=t.sender_name or "",
        recipient_name=t.recipient_name or "",
        country=t.country or "",
        confirm_number=t.confirm_number or "",
        send_amount=float(t.send_amount or 0),
        fee=float(t.fee or 0),
        federal_tax=float(t.federal_tax or 0),
        total_collected=float(t.total_collected),
        status=t.status or "Sent",
        batch_id=t.batch_id or "",
        employee_name=t.employee_name or "",
    )


@router.get("", response_model=TransferListResponse)
def list_route(
    store_ids: str = Query(
        ...,
        description=(
            "Comma-separated store IDs, e.g. `1,2`. Single-store "
            "admins pass one; multi-store owners pass every store "
            "in their umbrella."
        ),
    ),
    company: str = Query(""),
    status: str = Query(""),
    date_from: str = Query(""),
    date_to: str = Query(""),
    sender: str = Query(""),
    recipient: str = Query(""),
    country: str = Query(""),
    confirm: str = Query(""),
    batch: str = Query(""),
    q: str = Query("", description="Global search across sender/recipient/confirm/country/batch."),
    sort: str = Query("", description="Column slug to sort by; empty falls back to send_date desc."),
    dir: str = Query("desc", pattern="^(asc|desc)$"),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db),
) -> TransferListResponse:
    ids = _parse_store_ids(store_ids)
    filters = TransferFilters.from_query({
        "company": company, "status": status,
        "date_from": date_from, "date_to": date_to,
        "sender": sender, "recipient": recipient,
        "country": country, "confirm": confirm, "batch": batch,
        "q": q, "sort": sort, "dir": dir,
    })
    page_obj = list_transfers(
        db, ids, filters, page=page, per_page=per_page,
    )
    return TransferListResponse(
        rows=[_to_row(r) for r in page_obj.rows],
        total=page_obj.total,
        page=page_obj.page,
        per_page=page_obj.per_page,
        total_pages=page_obj.total_pages,
        page_amount=page_obj.page_amount,
    )


@router.get("/{transfer_id}", response_model=TransferResponse)
def get_route(
    transfer_id: int = Path(..., ge=1),
    store_ids: str = Query(
        ...,
        description=(
            "Caller's store scope, comma-separated. Cross-tenant "
            "lookups return 404 (never 403 — keeps tenancy "
            "boundaries opaque)."
        ),
    ),
    db: Session = Depends(get_db),
) -> TransferResponse:
    ids = _parse_store_ids(store_ids)
    transfer = get_by_id_in_stores(db, transfer_id, ids)
    if transfer is None:
        raise HTTPException(status_code=404, detail="Transfer not found")
    return TransferResponse(transfer=_to_row(transfer))
