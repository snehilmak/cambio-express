"""Admin module — Controllers (FastAPI router).

Mounts at `/api/v2/admin/*`. Endpoints:

  GET /admin/store-info → the JWT principal's store row
  PUT /admin/store-info → update editable fields

JWT-required, scoped to the principal's store. Superadmin (no
store scope) → 403.
"""
from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request
from sqlalchemy.orm import Session

from api.Core.Database import get_db
from api.Modules.Auth.Controllers import get_principal
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


router = APIRouter()


def _require_store(claims: dict) -> int:
    sid = claims.get("store_id")
    if sid is None:
        raise HTTPException(
            status_code=403,
            detail=(
                "JWT does not carry a store scope. Sign in as a "
                "store admin or owner to manage settings."
            ),
        )
    return int(sid)


def _to_row(s) -> StoreInfoRow:
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
    )


@router.get("/store-info", response_model=StoreInfoResponse)
def get_store_info(
    db: Session = Depends(get_db),
    claims: dict = Depends(get_principal),
) -> StoreInfoResponse:
    store_id = _require_store(claims)
    store = find_store(db, store_id)
    if store is None:
        raise HTTPException(status_code=404, detail="Store not found")
    return StoreInfoResponse(store=_to_row(store))


@router.put("/store-info", response_model=StoreInfoResponse)
def update_store_info_route(
    body: StoreInfoUpdateRequest,
    db: Session = Depends(get_db),
    claims: dict = Depends(get_principal),
) -> StoreInfoResponse:
    """Update operator-editable store fields. Only the role
    `admin` (or superadmin / owner) is allowed — the legacy
    settings page is gated by `admin_required`. Cashiers
    (role `employee`) hitting this endpoint return 403."""
    if claims.get("role") not in ("admin", "owner", "superadmin"):
        raise HTTPException(
            status_code=403,
            detail="Only store admins can update store info",
        )
    store_id = _require_store(claims)
    store = find_store(db, store_id)
    if store is None:
        raise HTTPException(status_code=404, detail="Store not found")
    fields = body.model_dump(exclude_unset=True)
    try:
        update_store_info(db, store, fields)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    db.commit()
    return StoreInfoResponse(store=_to_row(store))


# ── Team roster ─────────────────────────────────────────────


def _require_admin_role(claims: dict) -> None:
    if claims.get("role") not in ("admin", "owner", "superadmin"):
        raise HTTPException(
            status_code=403,
            detail="Only store admins can manage the team roster",
        )


def _team_row(e) -> TeamMemberRow:
    return TeamMemberRow(
        id=e.id, name=e.name or "", is_active=bool(e.is_active),
    )


@router.get("/team", response_model=TeamListResponse)
def list_team_route(
    db: Session = Depends(get_db),
    claims: dict = Depends(get_principal),
) -> TeamListResponse:
    """All StoreEmployee rows for the JWT principal's store
    (active + inactive). Inactive rows are surfaced so the
    admin can reactivate them — the legacy "Processed by"
    dropdown filters to active separately."""
    store_id = _require_store(claims)
    rows = list_team(db, store_id)
    return TeamListResponse(members=[_team_row(r) for r in rows])


@router.post(
    "/team", response_model=TeamMemberRow, status_code=201,
)
def create_team_member_route(
    body: TeamMemberCreateRequest,
    db: Session = Depends(get_db),
    claims: dict = Depends(get_principal),
) -> TeamMemberRow:
    """Create a new active StoreEmployee row. Admin role
    required."""
    _require_admin_role(claims)
    store_id = _require_store(claims)
    try:
        row = add_team_member(db, store_id, body.name)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    db.commit()
    return _team_row(row)


@router.put(
    "/team/{employee_id}", response_model=TeamMemberRow,
)
def update_team_member_route(
    employee_id: int = Path(..., ge=1),
    body: TeamMemberUpdateRequest = ...,
    db: Session = Depends(get_db),
    claims: dict = Depends(get_principal),
) -> TeamMemberRow:
    """Rename and/or toggle active. Cross-store IDs → 404
    (opaque tenancy)."""
    _require_admin_role(claims)
    store_id = _require_store(claims)
    member = find_team_member(db, store_id, employee_id)
    if member is None:
        raise HTTPException(status_code=404, detail="Team member not found")
    fields = body.model_dump(exclude_unset=True)
    try:
        update_team_member(
            db, member,
            name=fields.get("name"),
            is_active=fields.get("is_active"),
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    db.commit()
    return _team_row(member)


@router.delete(
    "/team/{employee_id}", status_code=204,
)
def deactivate_team_member_route(
    employee_id: int = Path(..., ge=1),
    db: Session = Depends(get_db),
    claims: dict = Depends(get_principal),
) -> None:
    """Soft-delete: flips is_active=False. We never hard-delete
    StoreEmployee rows so historical employee_name / employee_id
    attribution on past Transfer rows survives."""
    _require_admin_role(claims)
    store_id = _require_store(claims)
    member = find_team_member(db, store_id, employee_id)
    if member is None:
        raise HTTPException(status_code=404, detail="Team member not found")
    deactivate_team_member(db, member)
    db.commit()


# ── Subscription add-ons ────────────────────────────────────


def _adapt_addon(key: str, addon: dict, *, is_active: bool) -> "AddonRow":
    return AddonRow(
        key=key,
        name=addon.get("name", key),
        price_label=addon.get("price_label", ""),
        tagline=addon.get("tagline", ""),
        status=addon.get("status", "live"),
        is_active=is_active,
    )


@router.get("/addons", response_model=AddonListResponse)
def list_addons_route(
    db: Session = Depends(get_db),
    claims: dict = Depends(get_principal),
) -> AddonListResponse:
    """List every available add-on for the principal's store with
    its is_active flag. has_paid_plan tells the SPA whether the
    Toggle button should be enabled — add-ons require an active
    Basic or Pro subscription per the legacy contract."""
    sid = _require_store(claims)
    from app import (
        ADDONS_CATALOG, store_addon_keys, store_feature_enabled,
        store_has_paid_plan,
    )
    store = find_store(db, sid)
    if store is None:
        raise HTTPException(status_code=404, detail="Store not found")
    active_keys = store_addon_keys(store)
    rows: list[AddonRow] = []
    for key, addon in ADDONS_CATALOG.items():
        # Hide flag-gated add-ons whose flag is OFF for this store.
        if not store_feature_enabled(store, f"addon_{key}"):
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
    claims: dict = Depends(get_principal),
) -> AddonToggleResponse:
    """Toggle an add-on for the principal's store. Mirrors the
    legacy /admin/subscription/addons/<key> form. Requires an
    active paid plan; coming-soon add-ons can be requested but
    not flipped on."""
    sid = _require_store(claims)
    from app import (
        ADDONS_CATALOG, store_addon_keys, store_has_paid_plan,
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
    else:
        keys.add(addon_key)
    store.addons = ",".join(sorted(keys))
    db.commit()
    return AddonToggleResponse(
        addon=_adapt_addon(addon_key, addon, is_active=(addon_key in keys)),
    )


@router.get("/tax-export/years", response_model=TaxExportYearsResponse)
def list_tax_export_years_route(
    db: Session = Depends(get_db),
    claims: dict = Depends(get_principal),
) -> TaxExportYearsResponse:
    """Years offered in the tax-pack year picker, plus the default
    selection (last calendar year). Powers the /app/admin/tax-export
    React page. The actual ZIP download still comes from the legacy
    Flask route /admin/tax-export.zip — that streams a multi-MB file
    via Flask's send_file path and is left intact for now."""
    store_id = _require_store(claims)
    years = tax_export_year_choices(db, store_id)
    return TaxExportYearsResponse(
        years=years, default_year=tax_export_default_year(years),
    )


# ── Operator audit log ──────────────────────────────────────


@router.get("/audit-log", response_model=AdminAuditLogResponse)
def get_admin_audit_log_route(
    target: str = Query("", max_length=40),
    action: str = Query("", max_length=40),
    user:   str = Query("", max_length=20),
    page:   int = Query(1, ge=1),
    db: Session = Depends(get_db),
    claims: dict = Depends(get_principal),
) -> AdminAuditLogResponse:
    """Merged operator + transfer audit feed for the principal's
    store. Powers /app/admin/audit-log. Filters mirror the legacy
    Flask page exactly: target=transfer|daily_report|batch,
    action=create|update|delete|lock|unlock|status_changed,
    user=<id>. `page` is 1-based; per-page is the legacy 50."""
    store_id = _require_store(claims)
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
    db: Session, *, claims: dict, action: str,
    target_user, summary: str,
) -> None:
    """Record a per-store operator-audit row for a user mutation.

    Mirrors invariant #7 (every mutating admin endpoint records
    audit) — the legacy `admin_new_user` / `admin_edit_user`
    routes pre-date the audit table, so this Service-level audit
    is the SPA's cutover-time addition. target_type 'user' is
    truncated to 30 chars by the recorder, well under the limit.
    """
    from api.Modules.Audit.Services import record_operator_action
    sid = int(claims.get("store_id") or 0)
    record_operator_action(
        db,
        store_id=sid,
        user_id=int(claims.get("sub") or 0) or None,
        user_name=str(claims.get("username") or claims.get("full_name") or ""),
        user_role=str(claims.get("role") or ""),
        target_type="user",
        target_id=str(target_user.id),
        target_label=(target_user.username or "")[:160],
        action=action,
        summary=summary,
    )


@router.get("/users", response_model=AdminUserListResponse)
def list_users_route(
    db: Session = Depends(get_db),
    claims: dict = Depends(get_principal),
) -> AdminUserListResponse:
    """All User rows for the JWT principal's store. Powers the
    /app/admin/users roster. Includes inactive rows so admins
    can spot + reactivate them — the SPA filters/badges them
    in the UI."""
    _require_admin_role(claims)
    store_id = _require_store(claims)
    rows = list_store_users(db, store_id)
    return AdminUserListResponse(rows=[_user_row(u) for u in rows])


@router.post(
    "/users", response_model=AdminUserRow, status_code=201,
)
def create_user_route(
    body: AdminUserCreateRequest,
    db: Session = Depends(get_db),
    claims: dict = Depends(get_principal),
) -> AdminUserRow:
    """Create a new User in the principal's store. Username must
    be unique within the store; password is hashed via
    `User.set_password` (never stored raw). Role limited to
    'admin' / 'employee'."""
    _require_admin_role(claims)
    store_id = _require_store(claims)
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
    claims: dict = Depends(get_principal),
) -> AdminUserDetailResponse:
    """Single-user fetch for the Edit form prefill. Cross-store
    IDs and unknown IDs both return 404 — opaque tenancy."""
    _require_admin_role(claims)
    store_id = _require_store(claims)
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
    claims: dict = Depends(get_principal),
) -> AdminUserRow:
    """Edit full_name, role, is_active, and (optionally) password.
    Self-edit guard: an admin cannot demote / deactivate their
    own account through this endpoint — that returns 422 with a
    field-level error so the SPA can render it inline. Cross-
    store IDs return 404."""
    _require_admin_role(claims)
    store_id = _require_store(claims)
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
    claims: dict = Depends(get_principal),
) -> ReferralCodeResponse:
    """Self-service referral payload for the principal's store.
    Lazily mints a ReferralCode if missing (per CLAUDE.md
    invariant #12 — paid plans only; trial → 409). Powers
    /app/account/referrals."""
    store_id = _require_store(claims)
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
