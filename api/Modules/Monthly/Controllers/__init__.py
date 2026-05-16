"""Monthly module — Controllers (FastAPI router).

Mounts at `/api/v2/monthly/*`. Read-side endpoints:

  GET /monthly/months         → list of (year, month) the store has logged
  GET /monthly/{year}/{month} → single-month P&L breakdown or 404

JWT-required, scoped to the principal's store. Superadmin (no
store scope) → 403. Write-side stays on Flask.
"""
from fastapi import APIRouter, Depends, HTTPException, Path
from sqlalchemy.orm import Session

from api.Core.Database import get_db
from api.Modules.Auth.Controllers import get_principal
from api.Modules.Auth.Services import resolve_store_scope
from api.Modules.Monthly.Models import MonthlyFinancial
from api.Modules.Monthly.Repositories import list_logged_months
from api.Modules.Monthly.Requests import (
    MonthLogged,
    MonthlyResponse,
    MonthlyRow,
    MonthlyUpdateRequest,
    MonthsLoggedResponse,
)
from api.Modules.Monthly.Services import (
    MonthlySummary,
    summarize_monthly,
    update_monthly,
)


router = APIRouter()


def _to_row(s: MonthlySummary) -> MonthlyRow:
    r = s.row
    # Build a kwarg dict for every Pydantic field by introspecting
    # MonthlyRow's annotations — keeps the adapter from drifting
    # if a column is added / removed.
    kw: dict = {
        "id": r.id, "store_id": r.store_id,
        "year": int(r.year), "month": int(r.month),
        "notes": r.notes or "",
        "total_income":   s.total_income,
        "total_expenses": s.total_expenses,
        "net_profit":     s.net_profit,
    }
    for f in MonthlyRow.model_fields:
        if f in kw:
            continue
        kw[f] = float(getattr(r, f, 0) or 0)
    return MonthlyRow(**kw)


@router.get("/months", response_model=MonthsLoggedResponse)
def months_route(
    db: Session = Depends(get_db),
    claims: dict = Depends(get_principal),
) -> MonthsLoggedResponse:
    store_id = resolve_store_scope(claims)
    pairs = list_logged_months(db, store_id)
    return MonthsLoggedResponse(
        months=[MonthLogged(year=y, month=m) for y, m in pairs],
    )


@router.get(
    "/{year}/{month}",
    response_model=MonthlyResponse,
)
def monthly_route(
    year: int = Path(..., ge=2000, le=2100),
    month: int = Path(..., ge=1, le=12),
    db: Session = Depends(get_db),
    claims: dict = Depends(get_principal),
) -> MonthlyResponse:
    store_id = resolve_store_scope(claims)
    summary = summarize_monthly(db, store_id, int(year), int(month))
    if summary is None:
        raise HTTPException(
            status_code=404,
            detail="No monthly P&L logged for this period",
        )
    return MonthlyResponse(report=_to_row(summary))


@router.put(
    "/{year}/{month}",
    response_model=MonthlyResponse,
)
def update_monthly_route(
    year: int = Path(..., ge=2000, le=2100),
    month: int = Path(..., ge=1, le=12),
    body: MonthlyUpdateRequest = ...,
    db: Session = Depends(get_db),
    claims: dict = Depends(get_principal),
) -> MonthlyResponse:
    """Save the editable monthly P&L fields. Server auto-derives
    daily-summed + return-check-net + bank-charge fields and
    overwrites client values for those — same locked-fields
    contract as the legacy /monthly/<year>/<month> POST.

    JWT-required. Principal's store_id MUST match the URL scope
    (cross-store / superadmin → 403). Admin role required (the
    legacy admin-side route is gated by admin_required).

    Auto-creates the row when missing.
    """
    if claims.get("role") not in ("admin", "owner", "superadmin"):
        raise HTTPException(
            status_code=403,
            detail="Only store admins can save monthly P&L.",
        )
    sid = resolve_store_scope(claims)
    payload = body.model_dump(exclude_unset=True)
    notes = payload.pop("notes", "")
    fields = {k: v for k, v in payload.items() if v is not None}
    update_monthly(
        db,
        store_id=sid, year=int(year), month=int(month),
        fields=fields, notes=notes,
    )
    db.commit()
    summary = summarize_monthly(db, sid, int(year), int(month))
    if summary is None:
        raise HTTPException(
            status_code=500, detail="Monthly disappeared after save",
        )
    return MonthlyResponse(report=_to_row(summary))
