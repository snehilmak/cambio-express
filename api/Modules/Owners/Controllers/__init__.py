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

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request
from sqlalchemy.orm import Session

from api.Core.Database import get_db
from api.Core.Pagination import PaginationParams, paginate, pagination_dep
from api.Modules.Auth.Controllers import get_principal
from api.Modules.Auth.Models import User
from api.Modules.Auth.Services.principal import require_permission
from api.Modules.Owners.Requests import (
    OwnerBulkAddUserRequest,
    OwnerBulkAddUserResponse,
    OwnerBulkAddUserResultRow,
    OwnerConnectCodeListResponse,
    OwnerConnectCodeResponse,
    OwnerConnectCodeRow,
    OwnerCrossStoreDefaultsRequest,
    OwnerCrossStoreResponse,
    OwnerCrossStoreResultRow,
    OwnerLocationsResponse,
    OwnerPLRollupResponse,
    OwnerPLRollupRow,
    OwnerPLRollupTotals,
    OwnerStoreCompanyChip,
    OwnerStoreRow,
    OwnerUnlinkRequest,
)
from api.Modules.Owners.Services import (
    apply_cross_store_defaults,
    bulk_add_user_to_stores,
    owner_locations_payload,
    owner_store_ids,
)
from typing import Any
from api.Core.Clock import utc_now


router = APIRouter()


def _require_owner_principal(db: Session, claims: dict[str, Any]) -> User:
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
    user = db.get(User, int(sub))
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
    claims: dict[str, Any] = Depends(get_principal),
) -> OwnerLocationsResponse:
    require_permission(claims, "reports", "read")
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
    claims: dict[str, Any] = Depends(get_principal),
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
    require_permission(claims, "reports", "read")
    user = _require_owner_principal(db, claims)
    today = date.today()
    y = year or today.year
    m = month or today.month

    from api.Modules.Monthly.Models import MonthlyFinancial
    from api.Modules.Tenancy.Models import Store
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
    claims: dict[str, Any] = Depends(get_principal),
) -> OwnerConnectCodeListResponse:
    """Every code the owner has minted (active + redeemed +
    revoked + expired). Newest first."""
    require_permission(claims, "settings", "read")
    user = _require_owner_principal(db, claims)
    from api.Modules.Owners.Repositories import (
        list_codes_for_owner, get_store_names_for_codes,
    )
    rows = list_codes_for_owner(db, user.id)
    sids = [r.used_by_store_id for r in rows if r.used_by_store_id]
    stores = get_store_names_for_codes(db, sids)
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
    claims: dict[str, Any] = Depends(get_principal),
) -> OwnerConnectCodeResponse:
    """Mint a new 8-character connect code with a 7-day TTL.
    Owner shares the code with the store admin out of band; the
    store admin redeems it on their settings page to link the
    store to the owner's umbrella."""
    require_permission(claims, "settings", "create")
    import secrets
    from datetime import timedelta
    user = _require_owner_principal(db, claims)
    from api.Modules.Tenancy.Models import OwnerConnectCode
    # 8 hex chars uppercased — collision-resistant + readable when
    # the owner reads it aloud.
    raw = secrets.token_hex(4).upper()
    c = OwnerConnectCode(
        owner_id=user.id,
        code=raw,
        expires_at=utc_now() + timedelta(days=7),
    )
    db.add(c); db.flush()
    from api.Core.Audit import audit_owner
    audit_owner(
        db, user, action="generate_connect_code",
        target_type="owner_connect_code", target_id=str(c.id),
        details=f"minted connect code (expires {c.expires_at.isoformat()})",
    )
    db.commit()
    return OwnerConnectCodeResponse(code=_adapt_code(c))


@router.post("/connect-codes/{code_id}/revoke",
              response_model=OwnerConnectCodeResponse)
def owner_connect_codes_revoke_route(
    code_id: int,
    db: Session = Depends(get_db),
    claims: dict[str, Any] = Depends(get_principal),
) -> OwnerConnectCodeResponse:
    """Revoke an unredeemed code so the recipient can't use it.
    Already-redeemed codes can't be revoked — that disconnect
    flow is /owner/unlink/{store_id} instead."""
    require_permission(claims, "settings", "update")
    user = _require_owner_principal(db, claims)
    from api.Modules.Owners.Repositories import find_owner_code
    c = find_owner_code(db, code_id, user.id)
    if c is None:
        raise HTTPException(status_code=404, detail="Connect code not found")
    if c.used_at is not None:
        raise HTTPException(
            status_code=409,
            detail="Already redeemed — use /owner/unlink/{store_id} to disconnect.",
        )
    # Audit only on the actual revoke transition (re-revoking an
    # already-revoked code is a no-op and shouldn't append a row).
    if c.revoked_at is None:
        c.revoked_at = utc_now()
        from api.Core.Audit import audit_owner
        audit_owner(
            db, user, action="revoke_connect_code",
            target_type="owner_connect_code", target_id=str(c.id),
            details=f"revoked code {c.code}",
        )
    db.commit()
    return OwnerConnectCodeResponse(code=_adapt_code(c))


from api.Core.RateLimit import limiter as _rate_limiter


@router.post(
    "/bulk-add-user", response_model=OwnerBulkAddUserResponse,
)
@_rate_limiter.limit("10/minute")
def owner_bulk_add_user_route(
    request: Request,
    body: OwnerBulkAddUserRequest,
    db: Session = Depends(get_db),
    claims: dict[str, Any] = Depends(get_principal),
) -> OwnerBulkAddUserResponse:
    """Create the same login at every store in ``body.store_ids``
    that's actually in the owner's umbrella. Per-store outcomes
    (created / skipped / rejected) come back in the response so
    the SPA can show a result table; we don't 4xx the whole
    request just because one store collided."""
    require_permission(claims, "users", "create")
    user = _require_owner_principal(db, claims)
    try:
        raw_results = bulk_add_user_to_stores(
            db,
            owner_id=user.id,
            store_ids=list(body.store_ids),
            username=body.username,
            password=body.password,
            full_name=body.full_name,
            role=body.role,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    # Audit one row per successful create. Skipped / rejected
    # don't get audit entries — nothing mutated.
    from api.Modules.Audit.Services import record_operator_action
    for r in raw_results:
        if r["status"] != "created":
            continue
        record_operator_action(
            db,
            store_id=r["store_id"],
            user_id=user.id,
            user_name=user.full_name or user.username,
            user_role=user.role,
            target_type="user",
            target_id="",
            target_label=body.username,
            action="create",
            summary=(
                f"Owner bulk-added {body.role} '{body.username}'"
            ),
        )
    db.commit()

    counts = {"created": 0, "skipped": 0, "rejected": 0}
    for r in raw_results:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    return OwnerBulkAddUserResponse(
        created=counts["created"],
        skipped=counts["skipped"],
        rejected=counts["rejected"],
        results=[OwnerBulkAddUserResultRow(**r) for r in raw_results],
    )


@router.post(
    "/cross-store-defaults", response_model=OwnerCrossStoreResponse,
)
@_rate_limiter.limit("10/minute")
def owner_cross_store_defaults_route(
    request: Request,
    body: OwnerCrossStoreDefaultsRequest,
    db: Session = Depends(get_db),
    claims: dict[str, Any] = Depends(get_principal),
) -> OwnerCrossStoreResponse:
    """Push the picked field defaults (fed-tax-rate, timezone,
    business hours, etc.) to every store in ``body.store_ids``
    that's in the owner's umbrella. Per-store outcomes
    (updated / rejected) come back in the response so the SPA
    can show a result table; one validation failure doesn't
    fail the whole batch. Stores outside the umbrella surface
    as ``rejected``."""
    require_permission(claims, "settings", "update")
    user = _require_owner_principal(db, claims)
    # Convert the Pydantic body to the dict the service wants,
    # skipping unset fields (so ``omit field`` differs from
    # ``set to null``).
    defaults = body.model_dump(exclude_unset=True, exclude={"store_ids"})
    if not defaults:
        raise HTTPException(
            status_code=422,
            detail="Pick at least one field to apply.",
        )
    try:
        raw_results = apply_cross_store_defaults(
            db,
            owner_id=user.id,
            store_ids=list(body.store_ids),
            defaults=defaults,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    # Audit the bulk push as one OperatorAuditLog row per
    # updated store — keeps the per-store admin audit log
    # consistent with the rest of the surface.
    from api.Modules.Audit.Services import record_operator_action
    field_summary = ", ".join(sorted(defaults.keys()))
    for r in raw_results:
        if r["status"] != "updated":
            continue
        record_operator_action(
            db,
            store_id=r["store_id"],
            user_id=user.id,
            user_name=user.full_name or user.username,
            user_role=user.role,
            target_type="store",
            target_id=str(r["store_id"]),
            target_label=r["store_name"],
            action="cross_store_update",
            summary=f"Owner bulk-updated fields: {field_summary}",
        )
    db.commit()

    counts = {"updated": 0, "rejected": 0}
    for r in raw_results:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    return OwnerCrossStoreResponse(
        updated=counts["updated"],
        rejected=counts["rejected"],
        results=[OwnerCrossStoreResultRow(**r) for r in raw_results],
    )


@router.post("/unlink/{store_id}", status_code=204)
def owner_unlink_store_route(
    body: OwnerUnlinkRequest,
    store_id: int,
    db: Session = Depends(get_db),
    claims: dict[str, Any] = Depends(get_principal),
) -> None:
    """Disconnect a store from the owner umbrella. Removes the
    StoreOwnerLink row; the store keeps all its data (transfers,
    P&L, etc.) but the owner can no longer see it."""
    require_permission(claims, "settings", "delete")
    _ = body  # request body is empty today, schema kept for future
    user = _require_owner_principal(db, claims)
    from api.Modules.Owners.Repositories import find_link
    link = find_link(db, user.id, store_id)
    if link is None:
        raise HTTPException(status_code=404, detail="Store not in umbrella")
    db.delete(link)
    # CLAUDE.md invariant #7 — store-scoped mutation needs an audit
    # row.  Disconnecting a store from the owner umbrella materially
    # changes who can see it, so the affected store's admin audit
    # feed should show that an owner unlinked them.
    from api.Modules.Audit.Services import record_operator_action
    from api.Modules.Tenancy.Models import Store
    target_store = db.get(Store, store_id)
    record_operator_action(
        db,
        store_id=store_id,
        user_id=int(user.id),
        user_name=user.full_name or user.username or "",
        user_role=user.role or "owner",
        target_type="store_owner_link",
        target_id=str(store_id),
        target_label=(getattr(target_store, "name", "") or "")[:160],
        action="owner_unlink_store",
        summary=(
            f"owner '{user.username}' removed this store from their umbrella"
        ),
    )
    db.commit()
    return None


# ── Owner report center index ──────────────────────────────


@router.get("/reports")
def owner_reports_route(
    db: Session = Depends(get_db),  # noqa: ARG001 — kept for symmetry
    claims: dict[str, Any] = Depends(get_principal),
):
    """Owner-prefixed report-center index. Same `_REPORT_CATEGORIES`
    registry the admin index uses, but with `endpoint_prefix='owner_'`
    so each report's drilldown URL points at the owner-mirror Flask
    route (the registered owner-side report renderers).

    Owner role required — admin or employee callers fall back to
    /api/v2/reports."""
    require_permission(claims, "reports", "read")
    from api.Modules.Reports.Controllers import _build_report_list
    if claims.get("role") != "owner":
        raise HTTPException(
            status_code=403,
            detail="Owner scope required for /owner/reports.",
        )
    return _build_report_list(prefix="owner_")


# ── Owner dashboard + store detail ─────────────────────────


def _safe_value(v):
    """JSON-coerce dates, datetimes, ORM rows, lists/dicts."""
    from datetime import date, datetime
    if isinstance(v, (date, datetime)):
        return v.isoformat()
    if isinstance(v, dict):
        return {k: _safe_value(x) for k, x in v.items()}
    if isinstance(v, list):
        return [_safe_value(x) for x in v]
    if hasattr(v, "__table__"):
        return {c.name: _safe_value(getattr(v, c.name))
                for c in v.__table__.columns}
    return v


def _require_owner(db: Session, claims: dict[str, Any]) -> User:
    return _require_owner_principal(db, claims)


@router.get("/dashboard")
def owner_dashboard_route(
    period: str = "month",
    db: Session = Depends(get_db),
    claims: dict[str, Any] = Depends(get_principal),
):
    """Owner dashboard payload — KPIs, multi-store rollup, daily
    series, return-check aging. Delegates to the existing
    `dashboard_context` Service so the SPA + legacy template can
    diverge later without forking aggregation logic.
    """
    require_permission(claims, "reports", "read")
    user = _require_owner(db, claims)
    if period not in ("today", "month", "year"):
        period = "month"
    from api.Modules.Owners.Services.dashboard_context import (
        dashboard_context,
    )
    ctx = dashboard_context(db, user, period)
    # Drop the User-instance entry so we don't accidentally serialize
    # internal columns (totp_secret, password_hash, etc.). The SPA
    # already has the identity from the JWT.
    ctx.pop("user", None)
    return {k: _safe_value(v) for k, v in ctx.items()}


@router.get("/store/{store_id}")
def owner_store_detail_route(
    store_id: int = Path(..., ge=1),
    period: str = "month",
    db: Session = Depends(get_db),
    claims: dict[str, Any] = Depends(get_principal),
):
    """Drill-down view for a single store the owner is linked to.
    Read-only. Returns period KPIs, the company breakdown, the
    30-day over/short + receipts series, and recent activity."""
    require_permission(claims, "reports", "read")
    from datetime import date as ddate, timedelta
    from api.Modules.DailyBook.Models import DailyReport
    from api.Modules.Tenancy.Models import Store, StoreOwnerLink
    from api.Modules.Transfers.Models import Transfer
    from api.Modules.Owners.Services import (
        OWNER_TRANSFER_EXCLUDED as _OWNER_TRANSFER_EXCLUDED,
        owner_period_window as _owner_period_window,
    )
    user = _require_owner(db, claims)
    link = db.query(StoreOwnerLink).filter_by(
        owner_id=user.id, store_id=store_id,
    ).first()
    if link is None:
        raise HTTPException(
            status_code=404, detail="That store is not linked to your account.",
        )
    if period not in ("today", "month", "year"):
        period = "month"
    today = ddate.today()
    start, end, prev_start, prev_end, prev_label = _owner_period_window(
        period, today,
    )
    store = db.get(Store, store_id)
    if store is None:
        raise HTTPException(status_code=404, detail="Store not found.")

    from sqlalchemy import func
    co_rows = db.query(
        Transfer.company,
        func.count(Transfer.id),
        func.coalesce(func.sum(Transfer.send_amount), 0.0),
        func.coalesce(func.sum(Transfer.fee), 0.0),
        func.coalesce(func.sum(Transfer.federal_tax), 0.0),
    ).filter(
        Transfer.store_id == store_id,
        Transfer.send_date >= start, Transfer.send_date <= end,
        Transfer.status.notin_(_OWNER_TRANSFER_EXCLUDED),
    ).group_by(Transfer.company).order_by(
        func.coalesce(func.sum(Transfer.send_amount), 0.0).desc()
    ).all()
    company_rows = [
        {"company": (co or "—"), "count": int(c),
         "volume": float(v or 0), "fees": float(f or 0),
         "tax": float(t or 0)}
        for co, c, v, f, t in co_rows
    ]
    period_count = sum(r["count"] for r in company_rows)
    period_volume = sum(r["volume"] for r in company_rows)
    period_fees = sum(r["fees"] for r in company_rows)
    period_tax = sum(r["tax"] for r in company_rows)

    from api.Modules.Owners.Services import owner_kpis
    prev_count, prev_volume, _ = owner_kpis(
        db, [store_id], prev_start, prev_end,
    )

    d30_ago = today - timedelta(days=29)
    daily_reports = db.query(DailyReport).filter(
        DailyReport.store_id == store_id,
        DailyReport.report_date >= d30_ago,
        DailyReport.report_date <= today,
    ).all()
    by_day = {r.report_date: r for r in daily_reports}
    daily_labels, over_short_data, receipts_data = [], [], []
    for i in range(29, -1, -1):
        d = today - timedelta(days=i)
        r = by_day.get(d)
        daily_labels.append(d.isoformat())
        over_short_data.append(round(float(r.over_short) if r else 0.0, 2))
        receipts_data.append(round(
            float(r.total_receipts) if r else 0.0, 2,
        ))

    recent_transfers = (
        db.query(Transfer).filter_by(store_id=store_id)
        .order_by(Transfer.created_at.desc()).limit(10).all()
    )

    period_over_short = float(db.query(
        func.coalesce(func.sum(DailyReport.over_short), 0.0)
    ).filter(
        DailyReport.store_id == store_id,
        DailyReport.report_date >= start, DailyReport.report_date <= end,
    ).scalar() or 0.0)

    return {
        "store": {
            "id": store.id, "name": store.name, "slug": store.slug,
            "plan": store.plan,
        },
        "period": period, "prev_label": prev_label,
        "period_start": start.isoformat(), "period_end": end.isoformat(),
        "company_rows": company_rows,
        "period_count": period_count,
        "period_volume": period_volume,
        "period_fees": period_fees,
        "period_tax": period_tax,
        "period_over_short": period_over_short,
        "prev_count": prev_count, "prev_volume": prev_volume,
        "daily_labels": daily_labels,
        "over_short_data": over_short_data,
        "receipts_data": receipts_data,
        "recent_transfers": [
            {
                "id": t.id, "send_date": t.send_date.isoformat(),
                "sender_name": t.sender_name,
                "recipient_name": t.recipient_name,
                "company": t.company,
                "send_amount": float(t.send_amount or 0),
                "country": t.country,
                "status": t.status,
            }
            for t in recent_transfers
        ],
    }


# ── Owner user management ──────────────────────────────────


@router.get("/users")
def owner_users_route(
    store_id: int | None = Query(None, ge=1),
    q: str = Query("", max_length=100),
    pagination: PaginationParams = Depends(pagination_dep),
    db: Session = Depends(get_db),
    claims: dict[str, Any] = Depends(get_principal),
):
    """List users across all stores in the owner's umbrella.
    Optional store_id filter narrows to one store."""
    require_permission(claims, "users", "read")
    user = _require_owner_principal(db, claims)
    sids = owner_store_ids(db, user)
    if not sids:
        return {"rows": [], "total": 0, "page": 1, "total_pages": 0}
    if store_id is not None:
        if store_id not in sids:
            raise HTTPException(status_code=403, detail="Store not in your umbrella")
        sids = [store_id]

    from api.Modules.Owners.Repositories import (
        users_in_stores_query, get_store_names_map,
    )
    query = users_in_stores_query(db, sids, search=q)
    store_names = get_store_names_map(db, sids)
    return paginate(query, pagination, adapter=lambda u: {
        "id": u.id,
        "username": u.username,
        "full_name": u.full_name or "",
        "role": u.role or "",
        "is_active": bool(getattr(u, "is_active", True)),
        "store_id": u.store_id,
        "store_name": store_names.get(u.store_id, ""),
    })


# ── Owner store permissions ────────────────────────────────


@router.get("/store/{store_id}/permissions")
def owner_store_permissions_route(
    store_id: int = Path(..., ge=1),
    db: Session = Depends(get_db),
    claims: dict[str, Any] = Depends(get_principal),
) -> dict:
    """Get the permission matrix for a specific store in the owner's
    umbrella. Shows per-store overrides if any, else global defaults."""
    require_permission(claims, "settings", "read")
    user = _require_owner_principal(db, claims)
    sids = owner_store_ids(db, user)
    if store_id not in sids:
        raise HTTPException(status_code=403, detail="Store not in your umbrella")

    from api.Core.Permissions import get_permission_matrix
    visible_roles = ["admin", "employee"]
    editable_roles = ["employee"]
    return get_permission_matrix(store_id, visible_roles, editable_roles)


@router.put("/store/{store_id}/permissions")
def owner_update_store_permissions_route(
    store_id: int = Path(..., ge=1),
    body: dict = ...,
    db: Session = Depends(get_db),
    claims: dict[str, Any] = Depends(get_principal),
) -> dict:
    """Update per-store permission overrides for a store in the owner's
    umbrella. Owner can edit employee roles."""
    require_permission(claims, "settings", "update")
    user = _require_owner_principal(db, claims)
    sids = owner_store_ids(db, user)
    if store_id not in sids:
        raise HTTPException(status_code=403, detail="Store not in your umbrella")

    from api.Core.Permissions import (
        get_permission_matrix, set_store_permissions,
        RBAC_RESOURCES, RBAC_ACTIONS,
    )
    editable_roles = ["employee"]

    matrix = body.get("matrix", {})
    changes = body.get("changes", [])
    affected_roles: set[str] = set()

    if matrix:
        for role, resources in matrix.items():
            if role not in editable_roles:
                raise HTTPException(status_code=403, detail=f"Cannot edit {role} permissions")
            set_store_permissions(store_id, role, resources)
            affected_roles.add(role)
    elif changes:
        # Legacy diff mode: read current matrix, apply changes, write back
        current = get_permission_matrix(store_id, editable_roles, editable_roles)
        current_matrix = current["matrix"]
        for ch in changes:
            target_role = ch.get("role", "")
            resource = ch.get("resource", "")
            action = ch.get("action", "")
            allowed = ch.get("allowed", False)
            if target_role not in editable_roles:
                continue
            if resource not in RBAC_RESOURCES or action not in RBAC_ACTIONS:
                continue
            current_matrix[target_role][resource][action] = allowed
            affected_roles.add(target_role)
        for r in affected_roles:
            set_store_permissions(store_id, r, current_matrix[r])

    if affected_roles:
        from api.Modules.Audit.Services import record_operator_action
        record_operator_action(
            db,
            store_id=store_id,
            user_id=int(claims.get("sub", 0)),
            user_name=claims.get("full_name", ""),
            user_role=claims.get("role", ""),
            target_type="store_role_override",
            target_id=str(store_id),
            target_label=f"{len(matrix) + len(changes)} permission change(s)",
            action="update_store_permissions",
            summary=f"owner updated employee permissions for store {store_id}",
        )
        from api.Modules.Auth.Services.principal import invalidate_sessions_for_role
        for r in affected_roles:
            invalidate_sessions_for_role(db, store_id, r)
    db.commit()
    return owner_store_permissions_route(
        store_id=store_id, db=db, claims=claims,
    )


@router.post("/store/{store_id}/permissions/reset")
def owner_reset_store_permissions_route(
    store_id: int = Path(..., ge=1),
    body: dict = ...,
    db: Session = Depends(get_db),
    claims: dict[str, Any] = Depends(get_principal),
) -> dict:
    """Reset a role's permissions to global defaults for a store
    in the owner's umbrella."""
    require_permission(claims, "settings", "update")
    user = _require_owner_principal(db, claims)
    sids = owner_store_ids(db, user)
    if store_id not in sids:
        raise HTTPException(status_code=403, detail="Store not in your umbrella")
    target_role = body.get("role", "")
    if target_role not in ["employee"]:
        raise HTTPException(status_code=403, detail=f"Cannot reset {target_role} permissions")
    from api.Core.Permissions import reset_store_to_defaults
    reset_store_to_defaults(store_id, target_role)
    from api.Modules.Audit.Services import record_operator_action
    record_operator_action(
        db,
        store_id=store_id,
        user_id=int(claims.get("sub", 0)),
        user_name=claims.get("full_name", ""),
        user_role=claims.get("role", ""),
        target_type="store_role_override",
        target_id=str(store_id),
        target_label=f"reset {target_role} permissions",
        action="reset_store_permissions",
        summary=f"owner reset {target_role} permissions to global defaults for store {store_id}",
    )
    from api.Modules.Auth.Services.principal import invalidate_sessions_for_role
    invalidate_sessions_for_role(db, store_id, target_role)
    db.commit()
    return owner_store_permissions_route(
        store_id=store_id, db=db, claims=claims,
    )


# ── Cross-store activity stream ────────────────────────────


@router.get("/activity")
def owner_activity_route(
    store_id: int | None = Query(None, ge=1),
    q: str = Query("", max_length=100),
    pagination: PaginationParams = Depends(pagination_dep),
    db: Session = Depends(get_db),
    claims: dict[str, Any] = Depends(get_principal),
):
    """Activity stream across all stores in the owner's umbrella.
    Merges OperatorAuditLog + TransferAudit, newest first. Paginated."""
    require_permission(claims, "reports", "read")
    user = _require_owner_principal(db, claims)
    sids = owner_store_ids(db, user)
    if not sids:
        return {"rows": [], "total": 0, "page": 1, "total_pages": 0}
    if store_id is not None:
        if store_id not in sids:
            raise HTTPException(status_code=403, detail="Store not in your umbrella")
        sids = [store_id]

    from api.Modules.Audit.Models import OperatorAuditLog, TransferAudit
    from api.Modules.Owners.Repositories import get_store_names_map

    store_names = get_store_names_map(db, sids)

    needle = q.strip()

    oal_q = db.query(OperatorAuditLog).filter(
        OperatorAuditLog.store_id.in_(sids)
    )
    ta_q = db.query(TransferAudit).filter(
        TransferAudit.store_id.in_(sids)
    )
    if needle:
        like = f"%{needle}%"
        oal_q = oal_q.filter(
            OperatorAuditLog.summary.ilike(like)
            | OperatorAuditLog.user_name.ilike(like)
            | OperatorAuditLog.action.ilike(like)
        )
        ta_q = ta_q.filter(
            TransferAudit.summary.ilike(like)
            | TransferAudit.employee_name.ilike(like)
            | TransferAudit.action.ilike(like)
        )

    oal_rows = oal_q.order_by(OperatorAuditLog.created_at.desc()).limit(500).all()
    ta_rows = ta_q.order_by(TransferAudit.created_at.desc()).limit(500).all()

    merged: list[dict] = []
    for r in oal_rows:
        merged.append({
            "type": "audit",
            "store_id": r.store_id,
            "store_name": store_names.get(r.store_id, ""),
            "user_name": r.user_name or "",
            "user_role": r.user_role or "",
            "action": r.action or "",
            "target_type": r.target_type or "",
            "target_label": r.target_label or "",
            "summary": r.summary or "",
            "created_at": r.created_at.isoformat() if r.created_at else "",
        })
    for r in ta_rows:
        merged.append({
            "type": "transfer",
            "store_id": r.store_id,
            "store_name": store_names.get(r.store_id, ""),
            "user_name": r.employee_name or "",
            "user_role": "",
            "action": r.action or "",
            "target_type": "transfer",
            "target_label": str(r.transfer_id),
            "summary": r.summary or "",
            "created_at": r.created_at.isoformat() if r.created_at else "",
        })

    merged.sort(key=lambda x: x["created_at"], reverse=True)
    from api.Core.Pagination import paginate_list
    return paginate_list(merged, pagination)


# ── Bulk permission push ───────────────────────────────────


@router.post("/bulk-permissions")
@_rate_limiter.limit("10/minute")
def owner_bulk_permissions_route(
    request: Request,
    body: dict = ...,
    db: Session = Depends(get_db),
    claims: dict[str, Any] = Depends(get_principal),
) -> dict:
    """Push permission overrides to multiple stores at once.
    Only employee role is editable by owners."""
    require_permission(claims, "settings", "update")
    user = _require_owner_principal(db, claims)
    sids = owner_store_ids(db, user)
    if not sids:
        raise HTTPException(status_code=422, detail="No linked stores")

    target_ids: list[int] = body.get("store_ids", [])
    changes: list[dict] = body.get("changes", [])
    if not target_ids or not changes:
        raise HTTPException(status_code=422, detail="store_ids and changes required")

    from api.Core.Permissions import (
        get_permission_matrix, set_store_permissions,
        RBAC_RESOURCES, RBAC_ACTIONS,
    )
    editable_roles = ["employee"]

    results: list[dict] = []
    for sid in target_ids:
        if sid not in sids:
            results.append({"store_id": sid, "status": "rejected", "reason": "not in umbrella"})
            continue
        # Read current matrix, apply changes, write back
        current = get_permission_matrix(sid, editable_roles, editable_roles)
        current_matrix = current["matrix"]
        affected_roles: set[str] = set()
        applied = 0
        for ch in changes:
            target_role = ch.get("role", "")
            resource = ch.get("resource", "")
            action = ch.get("action", "")
            allowed = ch.get("allowed", False)
            if target_role not in editable_roles:
                continue
            if resource not in RBAC_RESOURCES or action not in RBAC_ACTIONS:
                continue
            old_val = current_matrix[target_role][resource][action]
            if old_val != allowed:
                current_matrix[target_role][resource][action] = allowed
                affected_roles.add(target_role)
                applied += 1
        for r in affected_roles:
            set_store_permissions(sid, r, current_matrix[r])
        if applied > 0:
            from api.Modules.Audit.Services import record_operator_action
            record_operator_action(
                db,
                store_id=sid,
                user_id=int(claims.get("sub", 0)),
                user_name=claims.get("full_name", ""),
                user_role=claims.get("role", ""),
                target_type="store_role_override",
                target_id=str(sid),
                target_label=f"{applied} permission change(s)",
                action="bulk_update_store_permissions",
                summary=f"owner bulk-pushed permissions to store {sid}",
            )
            from api.Modules.Auth.Services.principal import invalidate_sessions_for_role
            for r in affected_roles:
                invalidate_sessions_for_role(db, sid, r)
        results.append({"store_id": sid, "status": "applied", "changes": applied})
    db.commit()
    return {"results": results}
