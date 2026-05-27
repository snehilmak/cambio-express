"""Admin module — Controllers (FastAPI router).

Mounts at `/api/v2/admin/*`. Endpoints:

  GET /admin/store-info → the JWT principal's store row
  PUT /admin/store-info → update editable fields

JWT-required, scoped to the principal's store. Superadmin (no
store scope) → 403.
"""
from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, Response
from sqlalchemy.orm import Session

from api.Core.Database import get_db
from api.Modules.Auth.Controllers import get_principal
from api.Modules.Auth.Services import resolve_store_scope
from api.Modules.Auth.Services.principal import require_permission
from api.Modules.Admin.Repositories import (
    find_store,
    find_store_user,
    find_team_member,
    list_store_users,
    list_team,
)

from api.Modules.Admin.Requests import (
    AddonListResponse,
    AddonRow,
    AddonToggleResponse,
    AdminAuditLogResponse,
    AdminAuditRow,
    AdminAuditUserOption,
    AdminUserCreateRequest,
    AdminUserDetailResponse,
    AdminUserListResponse,
    AdminUserRow,
    AdminUserUpdateRequest,
    ReferralCodeResponse,
    ReferralRedemptionRow,
    StoreInfoResponse,
    StoreInfoRow,
    StoreInfoUpdateRequest,
    TaxExportYearsResponse,
    TeamListResponse,
    TeamMemberCreateRequest,
    TeamMemberRow,
    TeamMemberUpdateRequest,
)
from api.Modules.Admin.Services import (
    SelfDemotionError,
    TrialPlanError,
    UsernameTakenError,
    add_team_member,
    build_tax_pack_zip,
    create_store_user,
    deactivate_team_member,
    get_referral_payload,
    list_audit_rows,
    tax_export_default_year,
    tax_export_year_choices,
    update_store_info,
    update_store_user,
    update_team_member,
)
from typing import Any


router = APIRouter()


def _to_row(s) -> StoreInfoRow:
    # Lazy import — keeps Admin Controllers from pulling Services
    # at module-load time.
    from api.Modules.Admin.Services.store_info import ALLOWED_TIMEZONES
    from api.Modules.Admin.Services.store_hours import parse_stored_hours
    return StoreInfoRow(
        id=s.id,
        name=s.name or "",
        slug=s.slug or "",
        email=s.email or "",
        phone=s.phone or "",
        address=s.address or "",
        plan=s.plan or "trial",
        federal_tax_rate=float(s.federal_tax_rate or 0),
        is_active=bool(s.is_active),
        receipt_logo_url=s.receipt_logo_url or "",
        receipt_footer=s.receipt_footer or "",
        receipt_tax_id=s.receipt_tax_id or "",
        timezone=s.timezone or "",
        # Drop the leading "" sentinel for the SPA dropdown — the
        # UI surfaces "Use default" as its own option.
        timezone_choices=[tz for tz in ALLOWED_TIMEZONES if tz],
        # Always 7 entries — defaults fill in if the column is
        # NULL or malformed.
        store_hours=parse_stored_hours(s.store_hours),
        enforce_business_hours=bool(s.enforce_business_hours),
        timeclock_require_passkey=bool(
            getattr(s, "timeclock_require_passkey", False)
        ),
        timeclock_geofence_lat=getattr(s, "timeclock_geofence_lat", None),
        timeclock_geofence_lng=getattr(s, "timeclock_geofence_lng", None),
        timeclock_geofence_radius_m=int(
            getattr(s, "timeclock_geofence_radius_m", 100) or 100
        ),
        timeclock_require_geofence=bool(
            getattr(s, "timeclock_require_geofence", False)
        ),
        timeclock_late_minutes_threshold=int(
            getattr(s, "timeclock_late_minutes_threshold", 5) or 5
        ),
        legal_name=getattr(s, "legal_name", "") or "",
        ein=getattr(s, "ein", "") or "",
        business_address=getattr(s, "business_address", "") or "",
    )


@router.get("/store-info", response_model=StoreInfoResponse)
def get_store_info(
    db: Session = Depends(get_db),
    claims: dict[str, Any] = Depends(get_principal),
) -> StoreInfoResponse:
    require_permission(claims, "settings", "read")
    store_id = resolve_store_scope(claims)
    store = find_store(db, store_id)
    if store is None:
        raise HTTPException(status_code=404, detail="Store not found")
    from api.Modules.Billing.Services import (
        ensure_referral_code, store_has_paid_plan,
    )
    ref_code: str | None = None
    if store_has_paid_plan(store):
        rc = ensure_referral_code(db, store)
        if rc:
            ref_code = rc.code
    return StoreInfoResponse(store=_to_row(store), referral_code=ref_code)


@router.put("/store-info", response_model=StoreInfoResponse)
def update_store_info_route(
    body: StoreInfoUpdateRequest,
    db: Session = Depends(get_db),
    claims: dict[str, Any] = Depends(get_principal),
) -> StoreInfoResponse:
    """Update operator-editable store fields. Only the role
    `admin` (or superadmin / owner) is allowed — the legacy
    settings page is gated by `admin_required`. Cashiers
    (role `employee`) hitting this endpoint return 403."""
    require_permission(claims, "settings", "update")
    store_id = resolve_store_scope(claims)
    store = find_store(db, store_id)
    if store is None:
        raise HTTPException(status_code=404, detail="Store not found")
    fields = body.model_dump(exclude_unset=True)
    try:
        update_store_info(db, store, fields)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    if fields:
        # Summary lists the field names the operator touched (not the
        # values — addresses + tax rates are sensitive).  Materially-
        # important fields like `federal_tax_rate` + `timezone` need
        # a paper trail so a "wait, why are transfers calculating
        # differently?" question has an answer.
        _audit_admin_action(
            db, claims=claims, action="update_store_info",
            target_type="store",
            target_id=str(store.id),
            target_label=(store.name or "")[:160],
            summary=f"changed: {', '.join(sorted(fields.keys()))}",
        )
    db.commit()
    return StoreInfoResponse(store=_to_row(store))


# ── Team roster ─────────────────────────────────────────────


def _require_admin_role(claims: dict[str, Any]) -> None:
    if claims.get("role") not in ("admin", "owner", "superadmin"):
        raise HTTPException(
            status_code=403,
            detail="Only store admins can manage the team roster",
        )


def _team_row(e) -> TeamMemberRow:
    return TeamMemberRow(
        id=e.id, name=e.name or "", is_active=bool(e.is_active),
        hourly_rate=float(getattr(e, "hourly_rate", 0.0) or 0.0),
    )


@router.get("/team", response_model=TeamListResponse)
def list_team_route(
    db: Session = Depends(get_db),
    claims: dict[str, Any] = Depends(get_principal),
) -> TeamListResponse:
    """All StoreEmployee rows for the JWT principal's store
    (active + inactive). Inactive rows are surfaced so the
    admin can reactivate them — the legacy "Processed by"
    dropdown filters to active separately."""
    require_permission(claims, "users", "read")
    store_id = resolve_store_scope(claims)
    rows = list_team(db, store_id)
    return TeamListResponse(members=[_team_row(r) for r in rows])


@router.post(
    "/team", response_model=TeamMemberRow, status_code=201,
)
def create_team_member_route(
    body: TeamMemberCreateRequest,
    db: Session = Depends(get_db),
    claims: dict[str, Any] = Depends(get_principal),
) -> TeamMemberRow:
    """Create a new active StoreEmployee row."""
    require_permission(claims, "users", "create")
    store_id = resolve_store_scope(claims)
    try:
        row = add_team_member(
            db, store_id, body.name, hourly_rate=body.hourly_rate,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    _audit_admin_action(
        db, claims=claims, action="create_team_member",
        target_type="team_member",
        target_id=str(row.id),
        target_label=(row.name or "")[:160],
        summary=f"created at hourly_rate={float(row.hourly_rate or 0.0):.2f}",
    )
    db.commit()
    return _team_row(row)


@router.put(
    "/team/{employee_id}", response_model=TeamMemberRow,
)
def update_team_member_route(
    employee_id: int = Path(..., ge=1),
    body: TeamMemberUpdateRequest = ...,
    db: Session = Depends(get_db),
    claims: dict[str, Any] = Depends(get_principal),
) -> TeamMemberRow:
    """Rename and/or toggle active. Cross-store IDs → 404
    (opaque tenancy)."""
    require_permission(claims, "users", "update")
    store_id = resolve_store_scope(claims)
    member = find_team_member(db, store_id, employee_id)
    if member is None:
        raise HTTPException(status_code=404, detail="Team member not found")
    fields = body.model_dump(exclude_unset=True)
    try:
        update_team_member(
            db, member,
            name=fields.get("name"),
            is_active=fields.get("is_active"),
            hourly_rate=fields.get("hourly_rate"),
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    if fields:
        # Audit reflects which keys the operator submitted (rename /
        # reactivate / rate-change distinguish themselves cleanly in
        # the audit feed) without dumping sensitive values.
        action = (
            "reactivate_team_member"
            if fields.get("is_active") is True
            else "deactivate_team_member"
            if fields.get("is_active") is False
            else "update_team_member"
        )
        _audit_admin_action(
            db, claims=claims, action=action,
            target_type="team_member",
            target_id=str(member.id),
            target_label=(member.name or "")[:160],
            summary=f"changed: {', '.join(sorted(fields.keys()))}",
        )
    db.commit()
    return _team_row(member)


@router.delete(
    "/team/{employee_id}", status_code=204,
)
def deactivate_team_member_route(
    employee_id: int = Path(..., ge=1),
    db: Session = Depends(get_db),
    claims: dict[str, Any] = Depends(get_principal),
) -> None:
    """Soft-delete: flips is_active=False. We never hard-delete
    StoreEmployee rows so historical employee_name / employee_id
    attribution on past Transfer rows survives."""
    require_permission(claims, "users", "delete")
    store_id = resolve_store_scope(claims)
    member = find_team_member(db, store_id, employee_id)
    if member is None:
        raise HTTPException(status_code=404, detail="Team member not found")
    deactivate_team_member(db, member)
    _audit_admin_action(
        db, claims=claims, action="deactivate_team_member",
        target_type="team_member",
        target_id=str(member.id),
        target_label=(member.name or "")[:160],
        summary="soft-deleted (is_active=False)",
    )
    db.commit()


# ── Subscription add-ons ────────────────────────────────────


def _adapt_addon(key: str, addon: dict[str, Any], *, is_active: bool) -> "AddonRow":
    return AddonRow(
        key=key,
        name=addon.get("name", key),
        price_label=addon.get("price_label", ""),
        tagline=addon.get("tagline", ""),
        status=addon.get("status", "live"),
        is_active=is_active,
    )


@router.get("/subscription")
def subscription_summary_route(
    db: Session = Depends(get_db),
    claims: dict[str, Any] = Depends(get_principal),
):
    """Subscription page header data: current plan, trial status,
    retention countdown, account-snapshot fields, and the add-on
    catalog with each entry's `is_active` flag.

    Mirrors the legacy /admin/subscription Jinja context so the
    SPA can render the page without a second round-trip.
    """
    require_permission(claims, "settings", "read")
    sid = resolve_store_scope(claims)
    store = find_store(db, sid)
    if store is None:
        raise HTTPException(status_code=404, detail="Store not found")
    from api.Modules.Billing.Services import (
        ADDONS_CATALOG, DEFAULT_RETENTION_DAYS as DATA_RETENTION_DAYS,
        data_retention_days_left, get_trial_status, store_addon_keys,
        store_feature_enabled, store_has_paid_plan,
    )
    plan_labels = {
        "trial": "Free Trial", "basic": "Basic", "pro": "Pro",
        "inactive": "Inactive",
    }
    plan_prices = {"basic": "$35 / month", "pro": "$45 / month"}
    active_keys = store_addon_keys(store)
    addon_rows = []
    for key, addon in ADDONS_CATALOG.items():
        if not store_feature_enabled(db, store, f"addon_{key}"):
            continue
        addon_rows.append({
            "key": key,
            "name": addon.get("name", key),
            "price_label": addon.get("price_label", ""),
            "tagline": addon.get("tagline", ""),
            "description": addon.get("description", ""),
            "status": addon.get("status", "live"),
            "is_active": key in active_keys,
        })
    trial_status = (
        get_trial_status(store) if store.plan == "trial" else None
    )
    trial_days_left = None
    if store.plan == "trial" and store.trial_ends_at is not None:
        from datetime import datetime
        delta = store.trial_ends_at - datetime.utcnow()
        trial_days_left = max(0, delta.days)
    # Check with Stripe if the subscription is scheduled for
    # cancellation (cancel at end of billing period). This is a
    # lightweight API call — Stripe caches it and responds in <100ms.
    cancel_at_period_end = False
    cancel_at: str | None = None
    if store.stripe_subscription_id and store_has_paid_plan(store):
        try:
            import stripe
            sub = stripe.Subscription.retrieve(store.stripe_subscription_id)
            cancel_at_period_end = bool(sub.cancel_at_period_end)
            if cancel_at_period_end and sub.current_period_end:
                from datetime import datetime
                cancel_at = datetime.utcfromtimestamp(
                    sub.current_period_end
                ).strftime("%B %d, %Y")
        except Exception:
            pass

    # Referral code for the topbar crown. Only populated for paid
    # stores — the crown self-gates on plan, so trial/inactive
    # stores get None and the topbar hides the icon.
    referral_code_str: str | None = None
    if store_has_paid_plan(store):
        from api.Modules.Billing.Services import ensure_referral_code
        rc = ensure_referral_code(db, store)
        if rc:
            referral_code_str = rc.code

    return {
        "store": {
            "id": store.id,
            "name": store.name,
            "email": store.email,
            "plan": store.plan,
            "stripe_customer_id": store.stripe_customer_id,
            "stripe_subscription_id": store.stripe_subscription_id,
            "data_retention_until": (
                store.data_retention_until.isoformat()
                if store.data_retention_until else None
            ),
        },
        "plan_label": plan_labels.get(store.plan or "", "Unknown"),
        "plan_price": plan_prices.get(store.plan or "", ""),
        "has_paid_plan": store_has_paid_plan(store),
        "trial_status": trial_status,
        "trial_days_left": trial_days_left,
        "retention_days_left": data_retention_days_left(store),
        "retention_total_days": DATA_RETENTION_DAYS,
        "addons": addon_rows,
        "active_addon_count": len(active_keys),
        "cancel_at_period_end": cancel_at_period_end,
        "cancel_at": cancel_at,
        "referral_code": referral_code_str,
    }


@router.get("/addons", response_model=AddonListResponse)
def list_addons_route(
    db: Session = Depends(get_db),
    claims: dict[str, Any] = Depends(get_principal),
) -> AddonListResponse:
    """List every available add-on for the principal's store with
    its is_active flag. has_paid_plan tells the SPA whether the
    Toggle button should be enabled — add-ons require an active
    Basic or Pro subscription per the legacy contract."""
    require_permission(claims, "settings", "read")
    sid = resolve_store_scope(claims)
    from api.Modules.Billing.Services import (
        ADDONS_CATALOG,
        store_addon_keys, store_feature_enabled, store_has_paid_plan,
    )
    store = find_store(db, sid)
    if store is None:
        raise HTTPException(status_code=404, detail="Store not found")
    active_keys = store_addon_keys(store)
    rows: list[AddonRow] = []
    for key, addon in ADDONS_CATALOG.items():
        # Hide flag-gated add-ons whose flag is OFF for this store.
        if not store_feature_enabled(db, store, f"addon_{key}"):
            continue
        rows.append(_adapt_addon(
            key, addon, is_active=(key in active_keys),
        ))
    return AddonListResponse(
        rows=rows, total=len(rows),
        has_paid_plan=store_has_paid_plan(store),
    )


@router.post("/addons/{addon_key}/toggle", response_model=AddonToggleResponse)
def toggle_addon_route(
    addon_key: str,
    db: Session = Depends(get_db),
    claims: dict[str, Any] = Depends(get_principal),
) -> AddonToggleResponse:
    """Toggle an add-on for the principal's store. Mirrors the
    legacy /admin/subscription/addons/<key> form. Requires an
    active paid plan; coming-soon add-ons can be requested but
    not flipped on."""
    require_permission(claims, "settings", "update")
    sid = resolve_store_scope(claims)
    from api.Modules.Billing.Services import (
        ADDONS_CATALOG,
        store_addon_keys, store_has_paid_plan,
    )
    store = find_store(db, sid)
    if store is None:
        raise HTTPException(status_code=404, detail="Store not found")
    addon = ADDONS_CATALOG.get(addon_key)
    if addon is None:
        raise HTTPException(status_code=404, detail="Unknown add-on")
    if not store_has_paid_plan(store):
        raise HTTPException(
            status_code=409,
            detail="Add-ons require an active Basic or Pro subscription.",
        )
    if addon.get("status") == "coming_soon":
        raise HTTPException(
            status_code=409,
            detail=f"{addon.get('name', addon_key)} is coming soon.",
        )
    keys = store_addon_keys(store)
    if addon_key in keys:
        keys.discard(addon_key)
        new_state = "disabled"
    else:
        keys.add(addon_key)
        new_state = "enabled"
    store.addons = ",".join(sorted(keys))
    # Add-ons have a price — toggling them is a billable change, so
    # it deserves a paper trail even when the operator can flip it
    # themselves.
    _audit_admin_action(
        db, claims=claims, action=f"addon_{new_state}",
        target_type="addon",
        target_id=addon_key,
        target_label=str(addon.get("name") or addon_key)[:160],
        summary=f"{new_state} for store {store.slug or store.id}",
    )
    db.commit()
    return AddonToggleResponse(
        addon=_adapt_addon(addon_key, addon, is_active=(addon_key in keys)),
    )


@router.get("/tax-export/years", response_model=TaxExportYearsResponse)
def list_tax_export_years_route(
    db: Session = Depends(get_db),
    claims: dict[str, Any] = Depends(get_principal),
) -> TaxExportYearsResponse:
    """Years offered in the tax-pack year picker, plus the default
    selection (last calendar year). Powers the year dropdown on
    ``/app/admin/tax-export``."""
    require_permission(claims, "reports", "read")
    store_id = resolve_store_scope(claims)
    years = tax_export_year_choices(db, store_id)
    return TaxExportYearsResponse(
        years=years, default_year=tax_export_default_year(years),
    )


@router.get("/tax-export.zip")
def download_tax_pack_route(
    year: int = Query(
        ..., ge=2000, le=2100,
        description="Calendar year to pack (inclusive both ends).",
    ),
    db: Session = Depends(get_db),
    claims: dict[str, Any] = Depends(get_principal),
) -> Response:
    """Bundle a calendar year of store data into a ZIP and stream
    the bytes.

    Admin / owner / superadmin only — cashiers see the year picker
    in the UI but the download itself is gated server-side too.
    Store scope comes from the JWT, never a query param, so a
    cashier swapping the URL can't pivot to another store.

    Memory-bound — the ZIP is built in a ``BytesIO`` and returned
    in one shot. Operators export once a year, so the simpler
    in-memory path is fine; a streaming generator would only pay
    off on multi-GB packs."""
    require_permission(claims, "reports", "read")
    store_id = resolve_store_scope(claims)
    from api.Modules.Tenancy.Models import Store
    store = db.get(Store, store_id)
    if store is None:
        raise HTTPException(status_code=404, detail="Store not found.")
    payload = build_tax_pack_zip(db, store, year)
    slug = (store.slug or "store").replace("/", "-")
    filename = f"{slug}-tax-pack-{year}.zip"
    return Response(
        content=payload,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
        },
    )


# ── Operator audit log ──────────────────────────────────────


@router.get("/audit-log", response_model=AdminAuditLogResponse)
def get_admin_audit_log_route(
    target: str = Query("", max_length=40),
    action: str = Query("", max_length=40),
    user:   str = Query("", max_length=20),
    page:   int = Query(1, ge=1),
    db: Session = Depends(get_db),
    claims: dict[str, Any] = Depends(get_principal),
) -> AdminAuditLogResponse:
    """Merged operator + transfer audit feed for the principal's
    store. Powers /app/admin/audit-log. Filters mirror the legacy
    Flask page exactly: target=transfer|daily_report|batch,
    action=create|update|delete|lock|unlock|status_changed,
    user=<id>. `page` is 1-based; per-page is the legacy 50."""
    require_permission(claims, "reports", "read")
    store_id = resolve_store_scope(claims)
    payload = list_audit_rows(
        db, store_id=store_id,
        target_filter=target.strip(),
        action_filter=action.strip(),
        user_filter=user.strip(),
        page=page,
    )
    return AdminAuditLogResponse(
        rows=[AdminAuditRow(**r) for r in payload["rows"]],
        total=payload["total"],
        page=payload["page"],
        per_page=payload["per_page"],
        total_pages=payload["total_pages"],
        store_users=[
            AdminAuditUserOption(**u) for u in payload["store_users"]
        ],
        target_filter=target.strip(),
        action_filter=action.strip(),
        user_filter=user.strip(),
    )


@router.get("/audit-log.csv")
def export_admin_audit_log_csv_route(
    target: str = Query("", max_length=40),
    action: str = Query("", max_length=40),
    user:   str = Query("", max_length=20),
    db: Session = Depends(get_db),
    claims: dict[str, Any] = Depends(get_principal),
) -> Response:
    """CSV export of the operator audit feed for the principal's
    store.  Honors the same filter triplet as the paginated
    JSON endpoint above so the operator can preview filters in
    the UI, then click "Download CSV" to pull the same slice.

    Streams the full filtered set (no pagination) so a year-end
    compliance pull is one click — typical store has a few
    thousand rows / year which fits in memory comfortably.
    """
    require_permission(claims, "reports", "read")
    import csv as csv_lib
    import io
    from datetime import datetime as _datetime

    store_id = resolve_store_scope(claims)
    # Walk pagination to assemble the full filtered set —
    # ``list_audit_rows`` caps at 50 / page.
    page = 1
    all_rows: list[dict[str, Any]] = []
    while True:
        payload = list_audit_rows(
            db, store_id=store_id,
            target_filter=target.strip(),
            action_filter=action.strip(),
            user_filter=user.strip(),
            page=page,
        )
        all_rows.extend(payload["rows"])
        if page >= int(payload["total_pages"] or 1):
            break
        page += 1

    buf = io.StringIO()
    w = csv_lib.writer(buf)
    w.writerow([
        "Timestamp",
        "User",
        "Role",
        "Action",
        "Target type",
        "Target id",
        "Target label",
        "Summary",
        "Source",
    ])
    for r in all_rows:
        w.writerow([
            r.get("ts") or "",
            r.get("user_name") or "",
            r.get("user_role") or "",
            r.get("action") or "",
            r.get("target_type") or "",
            r.get("target_id") or "",
            r.get("target_label") or "",
            r.get("summary") or "",
            r.get("source") or "",
        ])
    today = _datetime.utcnow().strftime("%Y-%m-%d")
    return Response(
        content=buf.getvalue(),
        media_type="text/csv",
        headers={
            "Content-Disposition":
                f'attachment; filename="audit_log_{today}.csv"',
        },
    )


# ── Per-store user management ───────────────────────────────


def _user_row(u) -> AdminUserRow:
    return AdminUserRow(
        id=u.id,
        username=u.username or "",
        full_name=u.full_name or "",
        role=u.role or "employee",
        is_active=bool(u.is_active),
        created_at=u.created_at.isoformat() if u.created_at else "",
    )


def _audit_user_action(
    db: Session, *, claims: dict[str, Any], action: str,
    target_user, summary: str,
) -> None:
    """Record a per-store operator-audit row for a user mutation.

    Mirrors invariant #7 (every mutating admin endpoint records
    audit) — the legacy `admin_new_user` / `admin_edit_user`
    routes pre-date the audit table, so this Service-level audit
    is the SPA's cutover-time addition. target_type 'user' is
    truncated to 30 chars by the recorder, well under the limit.
    """
    _audit_admin_action(
        db, claims=claims, action=action,
        target_type="user",
        target_id=str(target_user.id),
        target_label=(target_user.username or "")[:160],
        summary=summary,
    )


def _audit_admin_action(
    db: Session, *, claims: dict[str, Any], action: str,
    target_type: str, target_id: str, target_label: str,
    summary: str,
) -> None:
    """Generic per-store operator-audit row.  CLAUDE.md invariant
    #7 — every mutating admin endpoint records audit — applies to
    the Admin module too, not just superadmin.  Callers that audit
    a User specifically should use the thinner `_audit_user_action`
    above so the call site reads at a glance.

    Use this for `Store` field edits, `StoreEmployee` roster CRUD,
    and the add-on toggle — any mutation that touches per-store
    operational state without going through the User path."""
    from api.Modules.Audit.Services import record_operator_action
    sid = int(claims.get("store_id") or 0)
    record_operator_action(
        db,
        store_id=sid,
        user_id=int(claims.get("sub") or 0) or None,
        user_name=str(claims.get("username") or claims.get("full_name") or ""),
        user_role=str(claims.get("role") or ""),
        target_type=target_type,
        target_id=target_id,
        target_label=target_label,
        action=action,
        summary=summary,
    )


@router.get("/users", response_model=AdminUserListResponse)
def list_users_route(
    db: Session = Depends(get_db),
    claims: dict[str, Any] = Depends(get_principal),
) -> AdminUserListResponse:
    """All User rows for the JWT principal's store. Powers the
    /app/admin/users roster. Includes inactive rows so admins
    can spot + reactivate them — the SPA filters/badges them
    in the UI."""
    require_permission(claims, "users", "read")
    store_id = resolve_store_scope(claims)
    rows = list_store_users(db, store_id)
    return AdminUserListResponse(rows=[_user_row(u) for u in rows])


@router.post(
    "/users", response_model=AdminUserRow, status_code=201,
)
def create_user_route(
    body: AdminUserCreateRequest,
    db: Session = Depends(get_db),
    claims: dict[str, Any] = Depends(get_principal),
) -> AdminUserRow:
    """Create a new User in the principal's store. Username must
    be unique within the store; password is hashed via
    `User.set_password` (never stored raw). Role limited to
    'admin' / 'employee'."""
    require_permission(claims, "users", "create")
    store_id = resolve_store_scope(claims)
    try:
        user = create_store_user(
            db, store_id=store_id,
            username=body.username,
            password=body.password,
            full_name=body.full_name,
            role=body.role,
        )
    except UsernameTakenError as exc:
        raise HTTPException(
            status_code=422,
            detail={"field_errors": {"username": str(exc)}},
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    _audit_user_action(
        db, claims=claims, action="create",
        target_user=user,
        summary=(
            f"created {user.role} user "
            f"{user.username!r}"
        ),
    )
    db.commit()
    return _user_row(user)


@router.get(
    "/users/{user_id}", response_model=AdminUserDetailResponse,
)
def get_user_route(
    user_id: int = Path(..., ge=1),
    db: Session = Depends(get_db),
    claims: dict[str, Any] = Depends(get_principal),
) -> AdminUserDetailResponse:
    """Single-user fetch for the Edit form prefill. Cross-store
    IDs and unknown IDs both return 404 — opaque tenancy."""
    require_permission(claims, "users", "read")
    store_id = resolve_store_scope(claims)
    user = find_store_user(db, store_id, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return AdminUserDetailResponse(user=_user_row(user))


@router.patch(
    "/users/{user_id}", response_model=AdminUserRow,
)
def update_user_route(
    user_id: int = Path(..., ge=1),
    body: AdminUserUpdateRequest = ...,
    db: Session = Depends(get_db),
    claims: dict[str, Any] = Depends(get_principal),
) -> AdminUserRow:
    """Edit full_name, role, is_active, and (optionally) password.
    Self-edit guard: an admin cannot demote / deactivate their
    own account through this endpoint — that returns 422 with a
    field-level error so the SPA can render it inline. Cross-
    store IDs return 404."""
    require_permission(claims, "users", "update")
    store_id = resolve_store_scope(claims)
    user = find_store_user(db, store_id, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    fields = body.model_dump(exclude_unset=True)
    actor_id_raw = claims.get("sub")
    actor_id = int(actor_id_raw) if actor_id_raw is not None else None
    try:
        update_store_user(
            db, user,
            full_name=fields.get("full_name"),
            role=fields.get("role"),
            is_active=fields.get("is_active"),
            password=fields.get("password"),
            actor_id=actor_id,
        )
    except SelfDemotionError as exc:
        # Surface as a field error — SPA renders inline next to
        # whichever field the operator tried to change.
        bad_field = "role" if "role" in fields else "is_active"
        raise HTTPException(
            status_code=422,
            detail={"field_errors": {bad_field: str(exc)}},
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    # Build a one-line summary listing which fields changed; keep
    # it short — recorder truncates at 2000 chars but the audit
    # page renders these inline.
    changed_keys = [k for k in fields if k != "password"]
    if "password" in fields and fields["password"]:
        changed_keys.append("password")
    summary = (
        f"updated user {user.username!r} "
        f"({', '.join(changed_keys) or 'no changes'})"
    )
    _audit_user_action(
        db, claims=claims, action="update",
        target_user=user, summary=summary,
    )
    db.commit()
    return _user_row(user)


# ── Referrals (paid-plan self-service share + earn) ─────────


@router.get("/referrals", response_model=ReferralCodeResponse)
def get_admin_referrals_route(
    request: Request,
    db: Session = Depends(get_db),
    claims: dict[str, Any] = Depends(get_principal),
) -> ReferralCodeResponse:
    """Self-service referral payload for the principal's store.
    Lazily mints a ReferralCode if missing (per CLAUDE.md
    invariant #12 — paid plans only; trial → 409). Powers
    /app/account/referrals."""
    store_id = resolve_store_scope(claims)
    # Build the share URL on the canonical host so the SPA copy
    # button always offers a public-facing link, even when the
    # admin is using a custom domain or Render preview URL.
    host_origin = (
        f"{request.url.scheme}://{request.url.netloc}"
    )
    try:
        payload = get_referral_payload(
            db, store_id=store_id, host_origin=host_origin,
        )
    except TrialPlanError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    db.commit()
    return ReferralCodeResponse(
        code=payload["code"],
        is_active=payload["is_active"],
        reward_self_cents=payload["reward_self_cents"],
        reward_referee_cents=payload["reward_referee_cents"],
        redeemed_count=payload["redeemed_count"],
        credits_earned_cents=payload["credits_earned_cents"],
        share_url=payload["share_url"],
        redemptions=[
            ReferralRedemptionRow(**r) for r in payload["redemptions"]
        ],
    )


# ── Per-store role permissions ─────────────────────────────


@router.get("/store-permissions")
def get_store_permissions_route(
    db: Session = Depends(get_db),
    claims: dict = Depends(get_principal),
) -> dict:
    """Get the effective permission matrix for this store.
    Shows per-store overrides if any, else global defaults."""
    require_permission(claims, "settings", "read")
    sid = resolve_store_scope(claims)
    role = claims.get("role", "")
    from api.Modules.Auth.Models import RolePermission, StoreRoleOverride
    from api.Modules.Auth.Services.login import (
        RBAC_ACTIONS, RBAC_DEFAULTS, RBAC_RESOURCES,
    )
    editable_roles = _editable_roles_for(role)
    visible_roles = ["admin", "employee"] if role != "superadmin" else ["admin", "employee", "owner"]

    global_granted: set[tuple[str, str, str]] = set()
    global_rows = db.query(RolePermission).all()
    for r in global_rows:
        global_granted.add((r.role, r.resource, r.action))
    if not global_granted:
        for rl, perms in RBAC_DEFAULTS.items():
            for perm in perms:
                res, act = perm.split(".", 1)
                global_granted.add((rl, res, act))

    store_rows = (
        db.query(StoreRoleOverride)
        .filter(StoreRoleOverride.store_id == sid)
        .all()
    )
    store_granted: set[tuple[str, str, str]] = set()
    store_has_overrides: set[str] = set()
    for r in store_rows:
        store_granted.add((r.role, r.resource, r.action))
        store_has_overrides.add(r.role)

    matrix: dict[str, dict[str, dict[str, bool]]] = {}
    for rl in visible_roles:
        matrix[rl] = {}
        source = store_granted if rl in store_has_overrides else global_granted
        for resource in RBAC_RESOURCES:
            matrix[rl][resource] = {}
            for action in RBAC_ACTIONS:
                matrix[rl][resource][action] = (rl, resource, action) in source

    return {
        "roles": visible_roles,
        "editable_roles": editable_roles,
        "resources": RBAC_RESOURCES,
        "actions": RBAC_ACTIONS,
        "matrix": matrix,
        "has_overrides": list(store_has_overrides),
    }


@router.put("/store-permissions")
def update_store_permissions_route(
    body: dict,
    db: Session = Depends(get_db),
    claims: dict = Depends(get_principal),
) -> dict:
    """Update per-store permission overrides. Only editable roles
    allowed (admin can only edit employee, owner can edit admin+employee)."""
    require_permission(claims, "settings", "update")
    sid = resolve_store_scope(claims)
    role = claims.get("role", "")
    editable_roles = _editable_roles_for(role)
    from api.Modules.Auth.Models import StoreRoleOverride
    from api.Modules.Auth.Services.login import RBAC_ACTIONS, RBAC_RESOURCES

    changes = body.get("changes", [])
    for ch in changes:
        target_role = ch.get("role", "")
        resource = ch.get("resource", "")
        action = ch.get("action", "")
        allowed = ch.get("allowed", False)
        if target_role not in editable_roles:
            raise HTTPException(403, f"Cannot edit {target_role} permissions")
        if resource not in RBAC_RESOURCES or action not in RBAC_ACTIONS:
            continue
        existing = (
            db.query(StoreRoleOverride)
            .filter_by(store_id=sid, role=target_role, resource=resource, action=action)
            .first()
        )
        if allowed and not existing:
            db.add(StoreRoleOverride(
                store_id=sid, role=target_role, resource=resource, action=action,
            ))
        elif not allowed and existing:
            db.delete(existing)
    db.commit()
    return get_store_permissions_route(db=db, claims=claims)


@router.post("/store-permissions/reset")
def reset_store_permissions_route(
    body: dict,
    db: Session = Depends(get_db),
    claims: dict = Depends(get_principal),
) -> dict:
    """Reset a role's permissions to global defaults (delete all overrides)."""
    require_permission(claims, "settings", "update")
    sid = resolve_store_scope(claims)
    role = claims.get("role", "")
    target_role = body.get("role", "")
    editable_roles = _editable_roles_for(role)
    if target_role not in editable_roles:
        raise HTTPException(403, f"Cannot reset {target_role} permissions")
    from api.Modules.Auth.Models import StoreRoleOverride
    db.query(StoreRoleOverride).filter_by(
        store_id=sid, role=target_role,
    ).delete()
    db.commit()
    return get_store_permissions_route(db=db, claims=claims)


def _editable_roles_for(caller_role: str) -> list[str]:
    """Which roles the caller can edit permissions for."""
    if caller_role == "superadmin":
        return ["admin", "employee", "owner"]
    if caller_role == "owner":
        return ["employee"]
    if caller_role == "admin":
        return ["employee"]
    return []


# ── Connect-code redemption (store admin) ──────────────────


@router.post("/redeem-connect-code")
def redeem_connect_code_route(
    body: dict,
    db: Session = Depends(get_db),
    claims: dict = Depends(get_principal),
) -> dict:
    """Store admin redeems an owner connect code to link this store
    to the owner's umbrella. Creates StoreOwnerLink + marks code used."""
    require_permission(claims, "settings", "update")
    sid = resolve_store_scope(claims)
    code_str = (body.get("code") or "").strip().upper()
    if not code_str:
        raise HTTPException(422, "Code is required")

    from datetime import datetime
    from api.Modules.Tenancy.Models import OwnerConnectCode, StoreOwnerLink, User

    occ = db.query(OwnerConnectCode).filter_by(code=code_str).first()
    if occ is None:
        raise HTTPException(404, "Code not found")
    if occ.revoked_at is not None:
        raise HTTPException(422, "Code has been revoked")
    if occ.used_at is not None:
        raise HTTPException(422, "Code has already been redeemed")
    if occ.expires_at and occ.expires_at < datetime.utcnow():
        raise HTTPException(422, "Code has expired")

    existing = db.query(StoreOwnerLink).filter_by(
        owner_id=occ.owner_id, store_id=sid,
    ).first()
    if existing:
        raise HTTPException(409, "Store is already linked to this owner")

    sub = claims.get("sub")
    link = StoreOwnerLink(owner_id=occ.owner_id, store_id=sid)
    db.add(link)
    occ.used_at = datetime.utcnow()
    occ.used_by_user_id = int(sub) if sub else None
    occ.used_by_store_id = sid

    owner = db.get(User, occ.owner_id)
    owner_name = (owner.full_name or owner.username or "") if owner else ""

    from api.Modules.Audit.Services import record_operator_action
    record_operator_action(
        db,
        store_id=sid,
        user_id=int(sub) if sub else 0,
        user_name=claims.get("full_name", ""),
        user_role=claims.get("role", ""),
        target_type="store_owner_link",
        target_id=str(occ.owner_id),
        target_label=owner_name[:160],
        action="redeem_owner_connect_code",
        summary=f"redeemed code {code_str} — linked to owner '{owner_name}'",
    )
    db.commit()
    return {"owner_name": owner_name}
