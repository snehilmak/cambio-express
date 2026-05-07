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
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from api.Core.Database import get_db
from api.Modules.Auth.Controllers import get_principal
from api.Modules.Batches.Requests import BatchListResponse, BatchRow
from api.Modules.Batches.Services import list_store_batches
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
