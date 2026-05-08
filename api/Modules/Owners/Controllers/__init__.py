"""Owners module — Controllers (FastAPI router).

Mounts at `/api/v2/owner/*`. First slice ships the locations
list — per-store stats for the multi-store owner umbrella view.

  GET /owner/locations?period=&q= → list owner's stores with
       period-scoped transfer count, volume, over/short, plus
       per-company chips.

Auth: requires JWT principal with role="owner" (or "superadmin"
for support/debug). Subsequent PRs add /owner/dashboard,
/owner/pl-rollup, /owner/store/{id} drill-down, and the
connect/unlink invitation flow.
"""
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from api.Core.Database import get_db
from api.Modules.Auth.Controllers import get_principal
from api.Modules.Auth.Models import User
from api.Modules.Owners.Requests import (
    OwnerLocationsResponse,
    OwnerPLRollupResponse,
    OwnerPLRollupRow,
    OwnerPLRollupTotals,
    OwnerStoreCompanyChip,
    OwnerStoreRow,
)
from api.Modules.Owners.Services import (
    owner_locations_payload,
    owner_store_ids,
)


router = APIRouter()


def _require_owner_principal(db: Session, claims: dict) -> User:
    """Resolve the JWT subject to a real User and gate on the owner
    role. Superadmin can hit owner endpoints too — useful for
    support / debug.

    Raises 403 if the role doesn't qualify, 401 if the sub is
    missing or doesn't resolve.
    """
    role = claims.get("role")
    if role not in ("owner", "superadmin"):
        raise HTTPException(
            status_code=403,
            detail="Only multi-store owners can access this resource.",
        )
    sub = claims.get("sub")
    if sub is None:
        raise HTTPException(
            status_code=401,
            detail="JWT is missing the subject claim.",
        )
    user = db.query(User).filter(User.id == int(sub)).one_or_none()
    if user is None:
        raise HTTPException(
            status_code=401,
            detail="JWT subject does not resolve to a user.",
        )
    return user


@router.get("/locations", response_model=OwnerLocationsResponse)
def owner_locations_route(
    period: str = Query("month", pattern="^(today|month|year)$"),
    q: str = Query("", description="Case-insensitive substring on store name"),
    db: Session = Depends(get_db),
    claims: dict = Depends(get_principal),
) -> OwnerLocationsResponse:
    user = _require_owner_principal(db, claims)
    rows, total = owner_locations_payload(db, user, period, q.strip() or None)
    out_rows = [
        OwnerStoreRow(
            store_id=r["store"].id,
            store_name=r["store"].name or "",
            store_slug=r["store"].slug or "",
            transfer_count=r["transfer_count"],
            volume=r["volume"],
            over_short=r["over_short"],
            report_count=r["report_count"],
            companies=[
                OwnerStoreCompanyChip(
                    company=c["company"],
                    count=c["count"],
                    volume=c["volume"],
                )
                for c in r.get("companies", [])
            ],
        )
        for r in rows
    ]
    return OwnerLocationsResponse(
        rows=out_rows, total=total, matched=len(out_rows),
    )


@router.get("/pl-rollup", response_model=OwnerPLRollupResponse)
def owner_pl_rollup_route(
    year: int | None = Query(None, ge=2000, le=2100),
    month: int | None = Query(None, ge=1, le=12),
    db: Session = Depends(get_db),
    claims: dict = Depends(get_principal),
) -> OwnerPLRollupResponse:
    """Side-by-side monthly P&L for every store in the owner umbrella.
    Mirrors the legacy /owner/pl-rollup view — one row per store with
    revenue / purchases / expenses / over-short / net-income, plus a
    totals footer. Rows sort by net income desc.

    `year` / `month` default to the current month when omitted. The
    response echoes them back so the SPA's pager has the canonical
    server-side values regardless of what the URL carried.

    `year_choices` lists every year with at least one P&L row across
    the umbrella so the UI can render a year-dropdown without a
    second roundtrip.
    """
    user = _require_owner_principal(db, claims)
    today = date.today()
    y = year or today.year
    m = month or today.month

    from app import MonthlyFinancial, Store
    sids = owner_store_ids(db, user)

    stores = (
        db.query(Store).filter(Store.id.in_(sids))
          .order_by(Store.name).all()
        if sids else []
    )
    pl_rows = (
        db.query(MonthlyFinancial)
          .filter(
              MonthlyFinancial.store_id.in_(sids),
              MonthlyFinancial.year == y,
              MonthlyFinancial.month == m,
          ).all()
        if sids else []
    )
    pl_by_store = {r.store_id: r for r in pl_rows}

    rows: list[OwnerPLRollupRow] = []
    totals = {"revenue": 0.0, "purchases": 0.0, "expenses": 0.0,
              "over_short": 0.0, "net": 0.0}
    for s in stores:
        pl = pl_by_store.get(s.id)
        if pl is not None:
            rev = float(pl.total_revenue or 0.0)
            pur = float(pl.total_purchases or 0.0)
            exp = float(pl.total_expenses or 0.0)
            os_ = float(pl.over_short or 0.0)
            net = float(pl.net_income or 0.0)
            has_pl = True
        else:
            rev = pur = exp = os_ = net = 0.0
            has_pl = False
        rows.append(OwnerPLRollupRow(
            store_id=s.id,
            store_name=s.name or "",
            store_slug=s.slug or "",
            has_pl=has_pl,
            revenue=rev, purchases=pur, expenses=exp,
            over_short=os_, net=net,
        ))
        totals["revenue"]    += rev
        totals["purchases"]  += pur
        totals["expenses"]   += exp
        totals["over_short"] += os_
        totals["net"]        += net

    rows.sort(key=lambda r: (r.net, -r.store_id), reverse=True)

    year_choices_set = {today.year}
    if sids:
        for (yy,) in (db.query(MonthlyFinancial.year)
                        .filter(MonthlyFinancial.store_id.in_(sids))
                        .distinct().all()):
            if yy is not None:
                year_choices_set.add(int(yy))

    return OwnerPLRollupResponse(
        year=y, month=m,
        rows=rows,
        totals=OwnerPLRollupTotals(**totals),
        year_choices=sorted(year_choices_set, reverse=True),
    )
