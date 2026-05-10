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
    OwnerConnectCodeListResponse,
    OwnerConnectCodeResponse,
    OwnerConnectCodeRow,
    OwnerLocationsResponse,
    OwnerPLRollupResponse,
    OwnerPLRollupRow,
    OwnerPLRollupTotals,
    OwnerStoreCompanyChip,
    OwnerStoreRow,
    OwnerUnlinkRequest,
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


# ── Owner connect codes (invite + revoke + unlink) ──────────


def _adapt_code(c, *, store_name: str = "") -> "OwnerConnectCodeRow":
    from datetime import datetime as _dt
    is_redeemed = c.used_at is not None
    is_revoked  = c.revoked_at is not None
    is_expired  = (
        not is_redeemed
        and not is_revoked
        and c.expires_at is not None
        and c.expires_at < _dt.utcnow()
    )
    return OwnerConnectCodeRow(
        id=c.id,
        code=c.code,
        created_at=c.created_at.isoformat() if c.created_at else "",
        expires_at=c.expires_at.isoformat() if c.expires_at else "",
        used_at=c.used_at.isoformat() if c.used_at else "",
        used_by_store_name=store_name,
        revoked_at=c.revoked_at.isoformat() if c.revoked_at else "",
        is_redeemed=is_redeemed,
        is_revoked=is_revoked,
        is_expired=is_expired,
    )


@router.get("/connect-codes", response_model=OwnerConnectCodeListResponse)
def owner_connect_codes_list_route(
    db: Session = Depends(get_db),
    claims: dict = Depends(get_principal),
) -> OwnerConnectCodeListResponse:
    """Every code the owner has minted (active + redeemed +
    revoked + expired). Newest first."""
    user = _require_owner_principal(db, claims)
    from app import OwnerConnectCode, Store
    rows = (
        db.query(OwnerConnectCode)
          .filter(OwnerConnectCode.owner_id == user.id)
          .order_by(OwnerConnectCode.created_at.desc())
          .all()
    )
    sids = [r.used_by_store_id for r in rows if r.used_by_store_id]
    stores = {
        s.id: s.name for s in
        db.query(Store).filter(Store.id.in_(sids)).all()
    } if sids else {}
    out = [
        _adapt_code(r, store_name=stores.get(r.used_by_store_id, ""))
        for r in rows
    ]
    return OwnerConnectCodeListResponse(rows=out, total=len(out))


@router.post(
    "/connect-codes",
    response_model=OwnerConnectCodeResponse, status_code=201,
)
def owner_connect_codes_generate_route(
    db: Session = Depends(get_db),
    claims: dict = Depends(get_principal),
) -> OwnerConnectCodeResponse:
    """Mint a new 8-character connect code with a 7-day TTL.
    Owner shares the code with the store admin out of band; the
    store admin redeems it on their settings page to link the
    store to the owner's umbrella."""
    import secrets
    from datetime import datetime, timedelta
    user = _require_owner_principal(db, claims)
    from app import OwnerConnectCode
    # 8 hex chars uppercased — collision-resistant + readable when
    # the owner reads it aloud.
    raw = secrets.token_hex(4).upper()
    c = OwnerConnectCode(
        owner_id=user.id,
        code=raw,
        expires_at=datetime.utcnow() + timedelta(days=7),
    )
    db.add(c); db.flush()
    db.commit()
    return OwnerConnectCodeResponse(code=_adapt_code(c))


@router.post("/connect-codes/{code_id}/revoke",
              response_model=OwnerConnectCodeResponse)
def owner_connect_codes_revoke_route(
    code_id: int,
    db: Session = Depends(get_db),
    claims: dict = Depends(get_principal),
) -> OwnerConnectCodeResponse:
    """Revoke an unredeemed code so the recipient can't use it.
    Already-redeemed codes can't be revoked — that disconnect
    flow is /owner/unlink/{store_id} instead."""
    from datetime import datetime
    user = _require_owner_principal(db, claims)
    from app import OwnerConnectCode
    c = (
        db.query(OwnerConnectCode)
          .filter(
              OwnerConnectCode.id == code_id,
              OwnerConnectCode.owner_id == user.id,
          )
          .one_or_none()
    )
    if c is None:
        raise HTTPException(status_code=404, detail="Connect code not found")
    if c.used_at is not None:
        raise HTTPException(
            status_code=409,
            detail="Already redeemed — use /owner/unlink/{store_id} to disconnect.",
        )
    if c.revoked_at is None:
        c.revoked_at = datetime.utcnow()
    db.commit()
    return OwnerConnectCodeResponse(code=_adapt_code(c))


@router.post("/unlink/{store_id}", status_code=204)
def owner_unlink_store_route(
    body: OwnerUnlinkRequest,
    store_id: int,
    db: Session = Depends(get_db),
    claims: dict = Depends(get_principal),
) -> None:
    """Disconnect a store from the owner umbrella. Removes the
    StoreOwnerLink row; the store keeps all its data (transfers,
    P&L, etc.) but the owner can no longer see it."""
    _ = body  # request body is empty today, schema kept for future
    user = _require_owner_principal(db, claims)
    from app import StoreOwnerLink
    link = (
        db.query(StoreOwnerLink)
          .filter(
              StoreOwnerLink.owner_id == user.id,
              StoreOwnerLink.store_id == store_id,
          )
          .one_or_none()
    )
    if link is None:
        raise HTTPException(status_code=404, detail="Store not in umbrella")
    db.delete(link)
    db.commit()
    return None


# ── Owner report center index ──────────────────────────────


@router.get("/reports")
def owner_reports_route(
    db: Session = Depends(get_db),  # noqa: ARG001 — kept for symmetry
    claims: dict = Depends(get_principal),
):
    """Owner-prefixed report-center index. Same `_REPORT_CATEGORIES`
    registry the admin index uses, but with `endpoint_prefix='owner_'`
    so each report's drilldown URL points at the owner-mirror Flask
    route (the registered owner-side report renderers).

    Owner role required — admin or employee callers fall back to
    /api/v2/reports."""
    from api.Modules.Reports.Controllers import _build_report_list
    if claims.get("role") != "owner":
        raise HTTPException(
            status_code=403,
            detail="Owner scope required for /owner/reports.",
        )
    return _build_report_list(prefix="owner_")
