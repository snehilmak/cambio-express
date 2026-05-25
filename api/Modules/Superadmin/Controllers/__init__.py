"""Superadmin module — Controllers (FastAPI router).

Mounts at `/api/v2/superadmin/*`. Endpoints:

  GET /superadmin/stores      → list every store with plan, trial
       state, retention timer, and Stripe linkage.
  GET /superadmin/audit-log   → paginated platform-wide audit log
       (every superadmin mutation, with actor + target).

Auth: requires JWT principal with role="superadmin". Subsequent
PRs add the controls dashboard, anomaly feed, discounts/
announcements/feature-flag CRUD, and impersonation.
"""
from math import ceil

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from sqlalchemy.orm import Session

from api.Core.Database import get_db
from api.Modules.Audit.Services import record_superadmin_action
from api.Modules.Auth.Controllers import get_principal
from api.Modules.Auth.Models import User
from api.Modules.Auth.Services import resolve_superadmin_user
from api.Modules.Superadmin.Requests import (
    DiscountCodeListResponse,
    DiscountCodeResponse,
    DiscountCodeRow,
    DiscountCodeToggleRequest,
    SuperadminAnomalyListResponse,
    SuperadminAnomalyRow,
    SuperadminAuditListResponse,
    SuperadminAuditRow,
    SuperadminReportCategory,
    SuperadminReportListResponse,
    SuperadminReportRow,
    SuperadminStoreCreateRequest,
    SuperadminStoreDetailResponse,
    SuperadminStoreDetailRow,
    SuperadminStoreListResponse,
    SuperadminStoreRow,
    SuperadminStoreUpdateRequest,
)
from typing import Any


router = APIRouter()


# CSV exports register first so `/reports/{slug}.csv` matches before
# the JSON drilldown's open-ended `/reports/{slug}` catch-all
# (Starlette picks the first declared route that matches).
from api.Modules.Reports.Controllers.csv_export import (  # noqa: E402
    register_superadmin as _register_superadmin_csv,
)

_register_superadmin_csv(router)


def _require_superadmin(claims: dict[str, Any]) -> None:
    if claims.get("role") != "superadmin":
        raise HTTPException(
            status_code=403,
            detail="Superadmin scope required.",
        )


def _audit_store(db: Session, user: User, action: str,
                 *, target_id: str = "", details: str = "") -> None:
    """Thin wrapper that goes straight to the Service so we don't need
    Flask's request context (the legacy `record_audit` reads
    `current_user()` from Flask session, which isn't set inside a
    FastAPI route through the dispatcher). Per CLAUDE.md invariant
    #7: every superadmin mutation MUST call record_audit."""
    record_superadmin_action(
        db,
        admin_id=user.id,
        admin_name=user.full_name or user.username or "",
        action=action,
        target_type="store",
        target_id=target_id,
        details=details,
    )


def _iso(dt) -> str:
    return dt.isoformat() if dt else ""


def _normalize_slug(raw: str) -> str:
    """Mirrors the legacy `superadmin_new_store` slug normalization:
    strip + lowercase + spaces-to-dashes. Centralized here so the
    create + patch paths agree on what 'the same slug' means."""
    return (raw or "").strip().lower().replace(" ", "-")


def _adapt_detail(s) -> SuperadminStoreDetailRow:
    return SuperadminStoreDetailRow(
        store_id=s.id,
        name=s.name or "",
        slug=s.slug or "",
        email=s.email or "",
        phone=s.phone or "",
        address=s.address or "",
        plan=s.plan or "trial",
        billing_cycle=s.billing_cycle or "",
        is_active=bool(s.is_active),
        federal_tax_rate=float(s.federal_tax_rate or 0.0),
        created_at=_iso(s.created_at),
        trial_ends_at=_iso(s.trial_ends_at),
        grace_ends_at=_iso(s.grace_ends_at),
        data_retention_until=_iso(s.data_retention_until),
        stripe_customer_id=s.stripe_customer_id or "",
        stripe_subscription_id=s.stripe_subscription_id or "",
    )


@router.get("/dashboard")
def dashboard_route(
    db: Session = Depends(get_db),
    claims: dict[str, Any] = Depends(get_principal),
) -> dict[str, Any]:
    """Platform-wide KPIs, signup trends, plan breakdown, transfer
    volume, and recent activity for the superadmin dashboard."""
    _require_superadmin(claims)
    from api.Modules.Superadmin.Services.dashboard import (
        superadmin_dashboard_context,
    )
    ctx = superadmin_dashboard_context(db)
    activity = []
    for a in ctx.get("activity", []):
        activity.append({
            "when": a["when"].isoformat() if a["when"] else "",
            "kind": a["kind"],
            "store_name": a["store_name"],
            "detail": a["detail"],
            "plan": a["plan"],
        })
    return {
        "total_stores": ctx["total_stores"],
        "active_count": ctx["active_count"],
        "trial_count": ctx["trial_count"],
        "paid_count": ctx["paid_count"],
        "inactive_count": ctx["inactive_count"],
        "estimated_mrr": ctx["estimated_mrr"],
        "new_stores_30d": ctx["new_stores_30d"],
        "new_stores_delta": ctx["new_stores_delta"],
        "churn_30d": ctx["churn_30d"],
        "churn_delta": ctx["churn_delta"],
        "basic_count": ctx["basic_count"],
        "pro_count": ctx["pro_count"],
        "basic_monthly": ctx["basic_monthly"],
        "basic_yearly": ctx["basic_yearly"],
        "pro_monthly": ctx["pro_monthly"],
        "pro_yearly": ctx["pro_yearly"],
        "basic_monthly_mrr": ctx["basic_monthly_mrr"],
        "basic_yearly_mrr": ctx["basic_yearly_mrr"],
        "pro_monthly_mrr": ctx["pro_monthly_mrr"],
        "pro_yearly_mrr": ctx["pro_yearly_mrr"],
        "signup_labels": ctx["signup_labels"],
        "signup_direct": ctx["signup_direct"],
        "signup_referral": ctx["signup_referral"],
        "plan_dist": ctx["plan_dist"],
        "volume_by_company": ctx["volume_by_company"],
        "total_volume_30d": ctx["total_volume_30d"],
        "total_transfers_30d": ctx["total_transfers_30d"],
        "top_referrers": ctx["top_referrers"],
        "direct_signups": ctx["direct_signups"],
        "referral_signups": ctx["referral_signups"],
        "activity": activity,
    }


# ── Permissions matrix ─────────────────────────────────────


@router.get("/permissions")
def get_permissions_route(
    db: Session = Depends(get_db),
    claims: dict[str, Any] = Depends(get_principal),
) -> dict[str, Any]:
    """Return the full RBAC matrix for the editor."""
    _require_superadmin(claims)
    from api.Modules.Auth.Models import RolePermission
    from api.Modules.Auth.Services.login import (
        RBAC_ACTIONS, RBAC_DEFAULTS, RBAC_RESOURCES,
    )
    rows = db.query(RolePermission).all()
    granted: set[tuple[str, str, str]] = set()
    for r in rows:
        granted.add((r.role, r.resource, r.action))
    if not granted:
        for role, perms in RBAC_DEFAULTS.items():
            for perm in perms:
                res, act = perm.split(".", 1)
                granted.add((role, res, act))
    matrix: dict[str, dict[str, dict[str, bool]]] = {}
    for role in ["admin", "employee", "owner"]:
        matrix[role] = {}
        for resource in RBAC_RESOURCES:
            matrix[role][resource] = {}
            for action in RBAC_ACTIONS:
                matrix[role][resource][action] = (
                    (role, resource, action) in granted
                )
    return {
        "roles": ["admin", "employee", "owner"],
        "resources": RBAC_RESOURCES,
        "actions": RBAC_ACTIONS,
        "matrix": matrix,
    }


@router.put("/permissions")
def update_permissions_route(
    body: dict[str, Any],
    db: Session = Depends(get_db),
    claims: dict[str, Any] = Depends(get_principal),
) -> dict[str, Any]:
    """Bulk-update the RBAC matrix. Body: {changes: [{role, resource, action, allowed}]}."""
    _require_superadmin(claims)
    from api.Modules.Auth.Models import RolePermission
    from api.Modules.Auth.Services.login import RBAC_ACTIONS, RBAC_RESOURCES
    sa = resolve_superadmin_user(db, claims)
    changes = body.get("changes", [])
    valid_roles = {"admin", "employee", "owner"}
    added = 0
    removed = 0
    for ch in changes:
        role = ch.get("role", "")
        resource = ch.get("resource", "")
        action = ch.get("action", "")
        allowed = ch.get("allowed", False)
        if role not in valid_roles:
            continue
        if resource not in RBAC_RESOURCES:
            continue
        if action not in RBAC_ACTIONS:
            continue
        existing = (
            db.query(RolePermission)
            .filter_by(role=role, resource=resource, action=action)
            .first()
        )
        if allowed and not existing:
            db.add(RolePermission(role=role, resource=resource, action=action))
            added += 1
        elif not allowed and existing:
            db.delete(existing)
            removed += 1
    db.commit()
    _audit_store(
        db, sa,
        "update_permissions",
        target_id="role_permission",
        details=f"Added {added}, removed {removed} permission grants",
    )
    return get_permissions_route(db=db, claims=claims)


# ── Global user management ─────────────────────────────────


@router.get("/users")
def list_users_route(
    q: str | None = Query(None),
    role: str | None = Query(None),
    store_id: int | None = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    claims: dict[str, Any] = Depends(get_principal),
) -> dict[str, Any]:
    """List all users across all stores with search + filters."""
    _require_superadmin(claims)
    from api.Modules.Tenancy.Models import Store, User
    query = db.query(User).outerjoin(Store, User.store_id == Store.id)
    if q:
        needle = f"%{q}%"
        query = query.filter(
            User.username.ilike(needle)
            | User.full_name.ilike(needle)
            | User.email.ilike(needle)
        )
    if role:
        query = query.filter(User.role == role)
    if store_id:
        query = query.filter(User.store_id == store_id)
    total = query.count()
    users = (
        query
        .add_columns(Store.name.label("store_name"))
        .order_by(User.created_at.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )
    rows = []
    for u, store_name in users:
        rows.append({
            "id": u.id,
            "username": u.username,
            "full_name": u.full_name or "",
            "email": u.email or "",
            "role": u.role or "",
            "store_id": u.store_id,
            "store_name": store_name or "",
            "is_active": bool(u.is_active),
            "has_2fa": bool(u.totp_enrolled_at),
            "last_login_at": _iso(u.last_login_at),
            "created_at": _iso(u.created_at),
        })
    return {
        "rows": rows,
        "total": total,
        "page": page,
        "total_pages": ceil(total / per_page),
    }


@router.post("/users/{user_id}/toggle-active")
def toggle_user_active_route(
    user_id: int = Path(..., ge=1),
    db: Session = Depends(get_db),
    claims: dict[str, Any] = Depends(get_principal),
) -> dict[str, Any]:
    """Enable / disable a user account."""
    _require_superadmin(claims)
    from api.Modules.Tenancy.Models import User
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(404, "User not found")
    if user.role == "superadmin":
        raise HTTPException(403, "Cannot disable superadmin")
    sa = resolve_superadmin_user(db, claims)
    user.is_active = not user.is_active
    db.commit()
    _audit_store(
        db, sa,
        "disable_user" if not user.is_active else "enable_user",
        target_id=str(user.id),
        details=f"User {user.username} (role={user.role})",
    )
    return {"ok": True, "is_active": user.is_active}


@router.post("/users/{user_id}/reset-2fa")
def reset_2fa_route(
    user_id: int = Path(..., ge=1),
    db: Session = Depends(get_db),
    claims: dict[str, Any] = Depends(get_principal),
) -> dict[str, Any]:
    """Force-clear a user's TOTP enrollment so they can re-enroll."""
    _require_superadmin(claims)
    from api.Modules.Tenancy.Models import User
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(404, "User not found")
    if user.role == "superadmin":
        raise HTTPException(403, "Cannot reset superadmin 2FA via API")
    sa = resolve_superadmin_user(db, claims)
    user.totp_secret = None
    user.totp_enrolled_at = None
    db.commit()
    _audit_store(
        db, sa,
        "reset_2fa",
        target_id=str(user.id),
        details=f"User {user.username}",
    )
    return {"ok": True}


@router.post("/users/{user_id}/force-password-reset")
def force_password_reset_route(
    user_id: int = Path(..., ge=1),
    db: Session = Depends(get_db),
    claims: dict[str, Any] = Depends(get_principal),
) -> dict[str, Any]:
    """Reset a user's password to a random temporary one and return it."""
    _require_superadmin(claims)
    from api.Modules.Tenancy.Models import User
    import secrets
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(404, "User not found")
    if user.role == "superadmin":
        raise HTTPException(403, "Cannot reset superadmin password via API")
    sa = resolve_superadmin_user(db, claims)
    temp_pw = secrets.token_urlsafe(12)
    user.set_password(temp_pw)
    db.commit()
    _audit_store(
        db, sa,
        "force_password_reset",
        target_id=str(user.id),
        details=f"User {user.username}",
    )
    return {"ok": True, "temp_password": temp_pw}


# ── Impersonation ──────────────────────────────────────────


@router.post("/impersonate/{user_id}")
def impersonate_route(
    user_id: int = Path(..., ge=1),
    db: Session = Depends(get_db),
    claims: dict[str, Any] = Depends(get_principal),
) -> dict[str, Any]:
    """Mint a short-lived JWT for impersonating another user.
    Audit-logged, 1-hour TTL, carries impersonated_by claim."""
    _require_superadmin(claims)
    from api.Modules.Auth.Services.jwt_issuer import JWTIssuer, issue_access_token
    from api.Modules.Auth.Services.login import permissions_for
    from api.Modules.Tenancy.Models import User
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(404, "User not found")
    if user.role == "superadmin":
        raise HTTPException(403, "Cannot impersonate superadmin")
    sa = resolve_superadmin_user(db, claims)
    issuer = JWTIssuer(
        sub=user.id,
        role=user.role or "employee",
        store_id=user.store_id,
        permissions=permissions_for(user.role or "employee"),
        full_name=user.full_name or "",
        username=user.username,
    )
    token = issue_access_token(issuer, ttl_seconds=3600)
    _audit_store(
        db, sa,
        "impersonate_user",
        target_id=str(user.id),
        details=f"User {user.username} (role={user.role}, store_id={user.store_id})",
    )
    return {
        "token": token,
        "user": {
            "id": user.id,
            "username": user.username,
            "role": user.role,
            "store_id": user.store_id,
            "full_name": user.full_name or "",
        },
    }


# ── System health ──────────────────────────────────────────


@router.get("/system-health")
def system_health_route(
    db: Session = Depends(get_db),
    claims: dict[str, Any] = Depends(get_principal),
) -> dict[str, Any]:
    """Platform health dashboard — DB, Stripe, SMTP, queue status."""
    _require_superadmin(claims)
    import os
    import platform
    from datetime import datetime

    from api.Modules.Tenancy.Models import Store, User
    from api.Modules.Transfers.Models import Transfer

    # DB stats
    total_users = db.query(User).count()
    total_stores = db.query(Store).count()
    total_transfers = db.query(Transfer).count()
    db_ok = True
    db_error = ""

    # Stripe health (wrapped — may hit the network)
    stripe_health: dict[str, Any] = {}
    try:
        from api.Modules.Billing.Services.health import check_stripe_integration
        stripe_health = check_stripe_integration()
    except Exception as e:
        stripe_health = {"ok": False, "error": str(e)[:200]}

    # SMTP / email health
    email_health: dict[str, Any] = {}
    try:
        from api.Modules.Notifications.Services.smtp import health_check
        raw = health_check(db)
        email_health = {
            "configured": raw.get("configured", False),
            "status": raw.get("status", "unknown"),
            "error": raw.get("error", ""),
            "recent_events": raw.get("recent_events", {}),
            "suppressed_count": raw.get("suppressed_count", 0),
            "last_event_at": (
                raw["last_event_at"].isoformat()
                if raw.get("last_event_at") else None
            ),
        }
    except Exception as e:
        email_health = {"configured": False, "error": str(e)[:200]}

    # Job queue
    queue_enabled = os.environ.get("JOB_QUEUE_ENABLED") == "1"
    redis_url = bool(os.environ.get("REDIS_URL"))

    # Rate limiting
    rate_limit_enabled = os.environ.get("RATELIMIT_ENABLED", "1") != "0"

    # Environment
    env_info = {
        "python_version": platform.python_version(),
        "platform": platform.platform(),
        "server_time": datetime.utcnow().isoformat(),
        "database_url_set": bool(os.environ.get("DATABASE_URL")),
        "secret_key_set": bool(os.environ.get("SECRET_KEY") or os.environ.get("AUTH_JWT_SECRET")),
        "sentry_dsn_set": bool(os.environ.get("SENTRY_DSN")),
        "webauthn_rp_id": os.environ.get("WEBAUTHN_RP_ID", "(auto)"),
    }

    return {
        "db": {
            "ok": db_ok,
            "error": db_error,
            "total_users": total_users,
            "total_stores": total_stores,
            "total_transfers": total_transfers,
        },
        "stripe": stripe_health,
        "email": email_health,
        "queue": {
            "enabled": queue_enabled,
            "redis_configured": redis_url,
        },
        "rate_limiting": {
            "enabled": rate_limit_enabled,
        },
        "env": env_info,
    }


@router.get("/stores", response_model=SuperadminStoreListResponse)
def list_stores_route(
    db: Session = Depends(get_db),
    claims: dict[str, Any] = Depends(get_principal),
) -> SuperadminStoreListResponse:
    _require_superadmin(claims)
    from api.Modules.Tenancy.Models import Store
    stores = db.query(Store).order_by(Store.created_at.desc()).all()
    rows = [
        SuperadminStoreRow(
            store_id=s.id,
            name=s.name or "",
            slug=s.slug or "",
            email=s.email or "",
            phone=s.phone or "",
            plan=s.plan or "trial",
            billing_cycle=s.billing_cycle or "",
            is_active=bool(s.is_active),
            created_at=_iso(s.created_at),
            trial_ends_at=_iso(s.trial_ends_at),
            grace_ends_at=_iso(s.grace_ends_at),
            data_retention_until=_iso(s.data_retention_until),
            stripe_customer_id=s.stripe_customer_id or "",
            stripe_subscription_id=s.stripe_subscription_id or "",
        )
        for s in stores
    ]
    return SuperadminStoreListResponse(rows=rows, total=len(rows))


@router.get("/stores/{store_id}", response_model=SuperadminStoreDetailResponse)
def get_store_route(
    store_id: int = Path(..., ge=1),
    db: Session = Depends(get_db),
    claims: dict[str, Any] = Depends(get_principal),
) -> SuperadminStoreDetailResponse:
    """Single-store payload for the SPA edit form.

    Read-only — feeds `/app/superadmin/stores/:id/edit`. Returns
    every field the edit form binds against (identity + plan +
    federal_tax_rate). 404 when the row doesn't exist."""
    _require_superadmin(claims)
    from api.Modules.Tenancy.Models import Store
    s = db.get(Store, store_id)
    if s is None:
        raise HTTPException(status_code=404, detail="Store not found")
    return SuperadminStoreDetailResponse(store=_adapt_detail(s))


@router.post(
    "/stores",
    response_model=SuperadminStoreDetailResponse,
    status_code=201,
)
def create_store_route(
    body: SuperadminStoreCreateRequest,
    db: Session = Depends(get_db),
    claims: dict[str, Any] = Depends(get_principal),
) -> SuperadminStoreDetailResponse:
    """Mint a new store + its initial admin user in one transaction.

    Mirrors the legacy `superadmin_new_store` POST handler: builds a
    `Store` row, attaches the operator-supplied admin User, and
    records a `create_store` audit entry. The transaction is atomic
    — if the admin User insert fails the Store row rolls back.

    Slug normalization (lowercase + dashes) matches the legacy
    handler. Duplicate slugs return 409 with `field=slug` so the SPA
    can render the field-level error inline."""
    user = resolve_superadmin_user(db, claims)
    from api.Modules.Tenancy.Models import Store
    slug = _normalize_slug(body.slug)
    if not slug:
        raise HTTPException(
            status_code=422,
            detail={"field": "slug", "message": "Slug cannot be empty."},
        )
    if db.query(Store).filter(Store.slug == slug).one_or_none():
        raise HTTPException(
            status_code=409,
            detail={
                "field": "slug",
                "message": f"Slug '{slug}' is already taken.",
            },
        )
    s = Store(
        name=body.name.strip(),
        slug=slug,
        email=body.email.strip(),
        phone=body.phone.strip(),
        address=body.address.strip(),
        plan=body.plan,
    )
    db.add(s)
    db.flush()
    a = User(
        store_id=s.id,
        username=body.admin_username.strip(),
        full_name=body.admin_name.strip(),
        role="admin",
    )
    a.set_password(body.admin_password)
    db.add(a)
    _audit_store(
        db, user, "create_store",
        target_id=str(s.id),
        details=s.slug,
    )
    db.commit()
    return SuperadminStoreDetailResponse(store=_adapt_detail(s))


@router.patch(
    "/stores/{store_id}",
    response_model=SuperadminStoreDetailResponse,
)
def update_store_route(
    body: SuperadminStoreUpdateRequest,
    store_id: int = Path(..., ge=1),
    db: Session = Depends(get_db),
    claims: dict[str, Any] = Depends(get_principal),
) -> SuperadminStoreDetailResponse:
    """Update an existing store's identity / plan fields.

    Every field is optional — only the keys present in the body get
    applied. Slug uniqueness is re-validated on rename (a duplicate
    returns 409 with `field=slug`). The audit row's `details` lists
    the keys that changed so the audit log shows what was touched
    even when the values are sensitive (email).

    Out of scope (use the dedicated endpoints):
      - Trial extension → POST /superadmin/stores/{id}/extend-trial
      - Toggle active   → POST /superadmin/stores/{id}/toggle-active
      - Comp plan       → POST /superadmin/stores/{id}/comp-plan
      - Add-on toggle   → POST /superadmin/stores/{id}/addons/...
    Those flows ship separately because they have their own audit
    actions + side effects (cancel-related state cleanup, retention
    timer reset, etc.)."""
    user = resolve_superadmin_user(db, claims)
    from api.Modules.Tenancy.Models import Store
    s = db.get(Store, store_id)
    if s is None:
        raise HTTPException(status_code=404, detail="Store not found")

    changed: list[str] = []
    if body.slug is not None:
        new_slug = _normalize_slug(body.slug)
        if not new_slug:
            raise HTTPException(
                status_code=422,
                detail={"field": "slug", "message": "Slug cannot be empty."},
            )
        if new_slug != s.slug:
            dup = (
                db.query(Store)
                  .filter(Store.slug == new_slug, Store.id != s.id)
                  .one_or_none()
            )
            if dup is not None:
                raise HTTPException(
                    status_code=409,
                    detail={
                        "field": "slug",
                        "message": f"Slug '{new_slug}' is already taken.",
                    },
                )
            s.slug = new_slug
            changed.append("slug")
    if body.name is not None and body.name.strip() != (s.name or ""):
        s.name = body.name.strip()
        changed.append("name")
    if body.email is not None and body.email.strip() != (s.email or ""):
        s.email = body.email.strip()
        changed.append("email")
    if body.phone is not None and body.phone.strip() != (s.phone or ""):
        s.phone = body.phone.strip()
        changed.append("phone")
    if body.address is not None and body.address.strip() != (s.address or ""):
        s.address = body.address.strip()
        changed.append("address")
    if body.plan is not None and body.plan != (s.plan or ""):
        s.plan = body.plan
        changed.append("plan")
    if (
        body.federal_tax_rate is not None
        and float(body.federal_tax_rate) != float(s.federal_tax_rate or 0.0)
    ):
        s.federal_tax_rate = float(body.federal_tax_rate)
        changed.append("federal_tax_rate")

    if changed:
        _audit_store(
            db, user, "update_store",
            target_id=str(s.id),
            details=",".join(changed),
        )
    db.commit()
    return SuperadminStoreDetailResponse(store=_adapt_detail(s))


@router.get("/audit-log", response_model=SuperadminAuditListResponse)
def list_audit_route(
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    action: str = Query("", description="Optional substring filter on action"),
    db: Session = Depends(get_db),
    claims: dict[str, Any] = Depends(get_principal),
) -> SuperadminAuditListResponse:
    """Paginated platform-wide audit log. Newest entries first.
    `action` is a case-insensitive substring filter so the
    superadmin can drill into a specific event type (e.g. "trial",
    "comp_plan", "feature_toggle"). The legacy report at
    `/superadmin/reports/audit-log` covers the same data; this
    endpoint feeds the SPA equivalent."""
    _require_superadmin(claims)
    from api.Modules.Audit.Models import SuperadminAuditLog
    q = db.query(SuperadminAuditLog)
    if action:
        q = q.filter(SuperadminAuditLog.action.ilike(f"%{action}%"))
    total = q.count()
    rows = (
        q.order_by(SuperadminAuditLog.created_at.desc())
         .offset((page - 1) * per_page)
         .limit(per_page)
         .all()
    )
    return SuperadminAuditListResponse(
        rows=[
            SuperadminAuditRow(
                id=r.id,
                admin_id=r.admin_id,
                admin_name=r.admin_name or "",
                action=r.action or "",
                target_type=r.target_type or "",
                target_id=r.target_id or "",
                details=r.details or "",
                created_at=_iso(r.created_at),
            )
            for r in rows
        ],
        total=total,
        page=page,
        per_page=per_page,
        total_pages=max(1, ceil(total / per_page)),
    )


@router.get("/anomalies", response_model=SuperadminAnomalyListResponse)
def list_anomalies_route(
    db: Session = Depends(get_db),
    claims: dict[str, Any] = Depends(get_principal),
) -> SuperadminAnomalyListResponse:
    """Read-only feed of platform-wide anomalies (quiet stores,
    big over/short variances) computed against today's date.

    Backed by `compute_platform_anomalies()` — same Service the
    legacy /superadmin/controls overview already runs on every
    page load. Cheap to recompute on each call.
    """
    _require_superadmin(claims)
    from api.Modules.Superadmin.Services import compute_platform_anomalies
    raw = compute_platform_anomalies(db)
    rows = [
        SuperadminAnomalyRow(
            kind=a["kind"],
            severity=a["severity"],
            store_id=a["store"].id,
            store_name=a["store"].name or "",
            store_slug=a["store"].slug or "",
            description=a["description"],
            href=a.get("href", ""),
        )
        for a in raw
    ]
    return SuperadminAnomalyListResponse(rows=rows, total=len(rows))


# ── Discount codes (list + toggle) ──────────────────────────


def _adapt_discount(d) -> DiscountCodeRow:
    from datetime import datetime as _dt
    expired = (
        d.expires_at is not None and d.expires_at < _dt.utcnow()
    )
    capped = (
        d.max_redemptions is not None
        and (d.redeemed_count or 0) >= d.max_redemptions
    )
    return DiscountCodeRow(
        id=d.id,
        code=d.code,
        label=d.label or "",
        percent_off=d.percent_off,
        amount_off_cents=d.amount_off_cents,
        value_label=d.value_label,
        duration=d.duration or "once",
        duration_in_months=d.duration_in_months,
        max_redemptions=d.max_redemptions,
        redeemed_count=d.redeemed_count or 0,
        expires_at=_iso(d.expires_at),
        is_active=bool(d.is_active),
        is_redeemable=bool(d.is_active) and not expired and not capped,
        stripe_coupon_id=d.stripe_coupon_id or "",
        stripe_promotion_code_id=d.stripe_promotion_code_id or "",
        created_at=_iso(d.created_at),
    )


@router.get("/discounts", response_model=DiscountCodeListResponse)
def list_discounts_route(
    db: Session = Depends(get_db),
    claims: dict[str, Any] = Depends(get_principal),
) -> DiscountCodeListResponse:
    """List every minted promo code (newest first). Read-only by
    design — Stripe coupon mint + new-code generation stays on the
    legacy site for now (those need careful Stripe error handling).
    This endpoint only renders + toggles; it never makes Stripe
    API calls."""
    _require_superadmin(claims)
    from api.Modules.Billing.Models import DiscountCode
    rows = (
        db.query(DiscountCode)
          .order_by(DiscountCode.created_at.desc())
          .all()
    )
    return DiscountCodeListResponse(
        rows=[_adapt_discount(d) for d in rows], total=len(rows),
    )


@router.post(
    "/discounts/{discount_id}/toggle",
    response_model=DiscountCodeResponse,
)
def toggle_discount_route(
    body: DiscountCodeToggleRequest,
    discount_id: int,
    db: Session = Depends(get_db),
    claims: dict[str, Any] = Depends(get_principal),
) -> DiscountCodeResponse:
    """Flip a discount's `is_active` flag without touching Stripe.
    Inactive codes still exist in the DB + Stripe (so historical
    invoices keep their references) but new Checkout sessions
    that try to apply them are rejected by `is_redeemable`."""
    user = resolve_superadmin_user(db, claims)
    from api.Modules.Billing.Models import DiscountCode
    d = db.query(DiscountCode).filter(
        DiscountCode.id == discount_id,
    ).one_or_none()
    if d is None:
        raise HTTPException(status_code=404, detail="Discount code not found")
    d.is_active = body.is_active
    # CLAUDE.md invariant #7: every superadmin mutation records an
    # audit entry. ``_audit_store`` is hardcoded to target_type="store";
    # this toggles a DiscountCode, so call the underlying service
    # directly with the right target_type.
    record_superadmin_action(
        db,
        admin_id=user.id,
        admin_name=user.full_name or user.username or "",
        action="toggle_discount",
        target_type="discount",
        target_id=str(d.id),
        details=f"code={d.code or ''}, is_active={body.is_active}",
    )
    db.commit()
    return DiscountCodeResponse(discount=_adapt_discount(d))


# ── Report center index ─────────────────────────────────────


@router.get("/reports", response_model=SuperadminReportListResponse)
def list_reports_route(
    db: Session = Depends(get_db),
    claims: dict[str, Any] = Depends(get_principal),
) -> SuperadminReportListResponse:
    """Platform-wide report-center categories (Platform Health,
    Revenue, Stripe, Trial Funnel, Feature Adoption, Support / Audit).
    Each report carries a Flask drilldown URL — the individual
    report templates haven't migrated yet, so the SPA links straight
    back into the legacy render path on click. As each report
    migrates, its URL will start pointing at /app/superadmin/reports/<slug>.

    The same registry that backs the legacy Jinja page is reused
    here (canonical home: ``api.Modules.Reports.Services.categories``)
    so categories never drift between the two surfaces."""
    _require_superadmin(claims)
    from api.Modules.Reports.Services.categories import (
        SUPERADMIN_REPORT_CATEGORIES, resolved_categories,
    )
    # Pure resolver — no Flask request context needed (every
    # superadmin drilldown is SPA-served, so the legacy ``url_for``
    # path always raised + fell through to the convention helper).
    resolved = resolved_categories(SUPERADMIN_REPORT_CATEGORIES)
    out: list[SuperadminReportCategory] = []
    for cat in resolved:
        out.append(SuperadminReportCategory(
            key=cat["key"],
            label=cat["label"],
            icon=cat["icon"],
            reports=[
                SuperadminReportRow(
                    key=r["key"],
                    label=r["label"],
                    description=r["description"],
                    url=r.get("url"),
                    status=r["status"],
                )
                for r in cat["reports"]
            ],
        ))
    return SuperadminReportListResponse(categories=out)


# ── Generic BI-drilldown endpoint ───────────────────────────
#
# The legacy Jinja superadmin drilldowns each had their own
# _make_superadmin_report_routes(...) registration with custom
# KPI lambdas + per-template renderers. To migrate the SPA in
# one shot, this single endpoint dispatches by slug into the
# matching Service function. The SPA's <SuperadminBIDrilldown>
# renders the result generically — KPIs are derived from the
# `totals` dict keys; columns from the first row's keys.

_SA_SERVICE_DISPATCH = {
    "active-stores-by-plan":    "active_stores_by_plan",
    "signup-funnel":            "signup_funnel",
    "login-activity":           "login_activity",
    "mrr-arr":                  "mrr_arr",
    "churn-cohort":             "churn_cohort",
    "conversion-rate":          "conversion_rate",
    "time-to-convert":          "time_to_convert",
    "trial-expiry-timing":      "trial_expiry_timing",
    "bank-sync-adoption":       "bank_sync_adoption",
    "tv-display-adoption":      "tv_display_adoption",
    "owner-adoption":           "owner_adoption",
    "passkey-adoption":         "passkey_adoption",
    "password-resets":          "password_resets",
    "suspended-stores":         "suspended_stores",
    "retention-queue":          "retention_queue",
    "refunds":                  "refunds",
    "failed-payments":          "failed_payments",
    "payouts":                  "payouts",
    "dau-mau":                  "dau_mau",
    "webhook-health":           "webhook_health",
}


@router.get("/reports/{slug}")
def superadmin_report_drilldown_route(
    slug: str,
    from_: str | None = Query(None, alias="from"),
    to: str | None = Query(None),
    db: Session = Depends(get_db),
    claims: dict[str, Any] = Depends(get_principal),
):
    """Generic drilldown for all superadmin BI reports. Dispatches by
    slug into the matching Service function in
    api.Modules.Superadmin.Services.

    Returns `{rows, totals}` (or `{rows, totals, ...extras}` when the
    service includes extras). The SPA renders KPIs from the totals
    keys and columns from the first row's keys — no per-slug config
    duplication.

    Unknown slugs return 404 so a typo doesn't fall back to a
    silently-empty page."""
    _require_superadmin(claims)
    fn_name = _SA_SERVICE_DISPATCH.get(slug)
    if fn_name is None:
        raise HTTPException(status_code=404, detail=f"Unknown report '{slug}'.")
    from datetime import date as _date, datetime as _dt
    today = _date.today()
    default_from = _date(today.year, today.month, 1)
    try:
        d_from = (
            _dt.strptime(from_, "%Y-%m-%d").date() if from_ else default_from
        )
    except ValueError:
        d_from = default_from
    try:
        d_to = _dt.strptime(to, "%Y-%m-%d").date() if to else today
    except ValueError:
        d_to = today
    if d_from > d_to:
        d_from, d_to = d_to, d_from

    import api.Modules.Superadmin.Services as svc
    service = getattr(svc, fn_name, None)
    if service is None:
        raise HTTPException(
            status_code=500,
            detail=f"Service '{fn_name}' is registered but not exported.",
        )
    result = service(db, d_from, d_to)
    # Most services return `(rows, totals)`; a few return three-tuples
    # for extras (e.g. dau-mau ships a series alongside totals).
    if isinstance(result, tuple):
        rows = result[0]
        totals = result[1] if len(result) > 1 else {}
        extras = result[2] if len(result) > 2 else {}
    else:
        # Defensive — if a future service returns a dict envelope,
        # forward it verbatim.
        return result
    payload = {"rows": rows, "totals": totals}
    if isinstance(extras, dict):
        payload.update(extras)
    return payload

