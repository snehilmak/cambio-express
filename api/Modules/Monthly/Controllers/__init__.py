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
from api.Modules.Monthly.Models import MonthlyFinancial
from api.Modules.Monthly.Repositories import list_logged_months
from api.Modules.Monthly.Requests import (
    MonthLogged,
    MonthlyResponse,
    MonthlyRow,
    MonthsLoggedResponse,
)
from api.Modules.Monthly.Services import (
    MonthlySummary,
    summarize_monthly,
)


router = APIRouter()


def _require_store_scope(claims: dict) -> int:
    sid = claims.get("store_id")
    if sid is None:
        raise HTTPException(
            status_code=403,
            detail=(
                "JWT does not carry a store scope. Sign in as a "
                "store admin or owner to view monthly P&L."
            ),
        )
    return int(sid)


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
    store_id = _require_store_scope(claims)
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
    store_id = _require_store_scope(claims)
    summary = summarize_monthly(db, store_id, int(year), int(month))
    if summary is None:
        raise HTTPException(
            status_code=404,
            detail="No monthly P&L logged for this period",
        )
    return MonthlyResponse(report=_to_row(summary))
