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
from sqlalchemy import func
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
    SuperadminStoreCreditRequest,
    SuperadminStoreCreditResponse,
    SuperadminStoreDetailResponse,
    SuperadminStoreDetailRow,
    SuperadminStoreListResponse,
    SuperadminStoreRow,
    SuperadminStoreUpdateRequest,
)
from typing import Any
from api.Core.Clock import utc_now


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
    """Record a superadmin action with target_type='store'.
    Delegates to ``api.Core.Audit.audit_superadmin``. Per CLAUDE.md
    invariant #7: every superadmin mutation MUST call record_audit."""
    from api.Core.Audit import audit_superadmin
    audit_superadmin(
        db, user,
        action=action,
        target_type="store",
        target_id=target_id,
        details=details,
    )


def _audit_and_commit(db: Session, user: User, action: str,
                      *, target_id: str = "", details: str = "") -> None:
    """Record a superadmin audit row and commit it in one call.

    The audit recorder only ``db.add()``s the row — it never
    flushes or commits (see ``api.Modules.Audit.Services.recorder``).
    So an audit row added *after* the route's own ``db.commit()``,
    or added with no commit at all, is silently rolled back by
    ``get_db()``'s ``finally: db.close()`` — the mutation lands but
    the audit trail doesn't, violating CLAUDE.md invariant #7.

    Every superadmin mutation MUST end with this helper (audit +
    commit together) instead of a bare ``db.commit()`` followed by a
    separate ``_audit_store(...)`` — co-locating the two makes it
    impossible for the ordering to drift back to the buggy form.
    Callers must have already applied their state changes to the
    session; this commits the audit row alongside them atomically."""
    _audit_store(db, user, action, target_id=target_id, details=details)
    db.commit()


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
        "mrr_trend": _compute_mrr_trend(db),
    }


def _compute_mrr_trend(db: Session) -> dict[str, Any]:
    """Approximate MRR for each of the last 12 months.

    Uses current paid-store counts as of today — doesn't track
    historical plan changes. Good enough for a trend chart until
    we add a monthly MRR snapshot table."""
    from datetime import date, timedelta
    from api.Modules.Superadmin.Services.dashboard import compute_mrr
    from api.Modules.Tenancy.Models import Store

    today = date.today()
    labels: list[str] = []
    values: list[int] = []
    for i in range(11, -1, -1):
        d = today.replace(day=1) - timedelta(days=i * 30)
        month_end = d.replace(day=28)
        stores = (
            db.query(Store.plan, Store.billing_cycle)
            .filter(
                Store.created_at <= month_end,
                Store.plan.in_(["basic", "pro"]),
            )
            .all()
        )
        bm = by = pm = py_ = 0
        for plan, cycle in stores:
            if plan == "basic":
                if cycle == "yearly":
                    by += 1
                else:
                    bm += 1
            elif plan == "pro":
                if cycle == "yearly":
                    py_ += 1
                else:
                    pm += 1
        _, _, _, _, total = compute_mrr(bm, by, pm, py_)
        labels.append(d.strftime("%b %Y"))
        values.append(total)
    return {"labels": labels, "values": values}


# ── Maintenance mode ───────────────────────────────────────


@router.get("/maintenance")
def get_maintenance_route(
    db: Session = Depends(get_db),
    claims: dict[str, Any] = Depends(get_principal),
) -> dict[str, Any]:
    _require_superadmin(claims)
    from api.Modules.Superadmin.Models import get_setting
    enabled = get_setting(db, "maintenance_mode", "false") == "true"
    message = get_setting(db, "maintenance_message", "")
    return {"enabled": enabled, "message": message}


@router.post("/maintenance")
def set_maintenance_route(
    body: dict[str, Any],
    db: Session = Depends(get_db),
    claims: dict[str, Any] = Depends(get_principal),
) -> dict[str, Any]:
    _require_superadmin(claims)
    from api.Modules.Superadmin.Models import set_setting
    sa = resolve_superadmin_user(db, claims)
    enabled = body.get("enabled", False)
    message = body.get("message", "")
    set_setting(db, "maintenance_mode", "true" if enabled else "false")
    set_setting(db, "maintenance_message", str(message)[:500])
    # `set_setting` already committed the settings; the audit row is
    # added afterward so it needs its own commit or `db.close()`
    # rolls it back (invariant #7).
    _audit_and_commit(
        db, sa,
        "maintenance_mode_toggle",
        target_id="platform",
        details=f"{'Enabled' if enabled else 'Disabled'}: {message[:100]}",
    )
    return {"enabled": enabled, "message": message}


# ── Permissions matrix ─────────────────────────────────────


@router.get("/permissions")
def get_permissions_route(
    db: Session = Depends(get_db),
    claims: dict[str, Any] = Depends(get_principal),
) -> dict[str, Any]:
    """Return the full RBAC matrix for the editor."""
    _require_superadmin(claims)
    from api.Core.Permissions import get_global_matrix
    return get_global_matrix()


@router.put("/permissions")
def update_permissions_route(
    body: dict[str, Any],
    db: Session = Depends(get_db),
    claims: dict[str, Any] = Depends(get_principal),
) -> dict[str, Any]:
    """Bulk-update the RBAC matrix. Body: {matrix: {role: {resource: {action: bool}}}}
    or legacy {changes: [{role, resource, action, allowed}]}."""
    _require_superadmin(claims)
    from api.Core.Permissions import (
        get_global_matrix, set_global_permissions,
        RBAC_RESOURCES, RBAC_ACTIONS,
    )
    sa = resolve_superadmin_user(db, claims)
    valid_roles = {"admin", "employee", "owner"}

    matrix = body.get("matrix", {})
    changes = body.get("changes", [])

    if matrix:
        # Full-state replacement per role
        affected_roles: set[str] = set()
        for role, resources in matrix.items():
            if role not in valid_roles:
                continue
            set_global_permissions(role, resources)
            affected_roles.add(role)
    elif changes:
        # Legacy diff mode: read current, apply changes, write back
        current = get_global_matrix()
        current_matrix = current["matrix"]
        affected_roles = set()
        for ch in changes:
            role = ch.get("role", "")
            resource = ch.get("resource", "")
            action = ch.get("action", "")
            allowed = ch.get("allowed", False)
            if role not in valid_roles:
                continue
            if resource not in RBAC_RESOURCES or action not in RBAC_ACTIONS:
                continue
            current_matrix[role][resource][action] = allowed
            affected_roles.add(role)
        for role in affected_roles:
            set_global_permissions(role, current_matrix[role])
    else:
        affected_roles = set()

    if affected_roles:
        # Invalidate sessions for affected roles globally
        from api.Modules.Auth.Models import RefreshToken
        from api.Modules.Tenancy.Models import User as _User
        now = utc_now()
        for r in affected_roles:
            db.query(RefreshToken).filter(
                RefreshToken.user_id.in_(
                    db.query(_User.id).filter(
                        _User.role == r,
                        _User.is_active.is_(True),
                    )
                ),
                RefreshToken.revoked_at.is_(None),
                RefreshToken.expires_at > now,
            ).update({"revoked_at": now}, synchronize_session="fetch")
    # Audit + commit together so the session-revocations and the
    # audit row land in one transaction. The bare `db.commit()` used
    # to sit *before* the audit (and only inside the `if`), so the
    # audit row was rolled back by `db.close()` (invariant #7).
    _audit_and_commit(
        db, sa,
        "update_permissions",
        target_id="role_permission",
        details=f"Updated global permissions for roles: {', '.join(sorted(affected_roles))}",
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


@router.post("/users/{user_id}/change-role")
def change_user_role_route(
    user_id: int = Path(..., ge=1),
    body: dict[str, Any] = {},
    db: Session = Depends(get_db),
    claims: dict[str, Any] = Depends(get_principal),
) -> dict[str, Any]:
    """Change a user's role. Valid roles: admin, employee, owner."""
    _require_superadmin(claims)
    from api.Modules.Tenancy.Models import User
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    if user.role == "superadmin":
        raise HTTPException(status_code=403, detail="Cannot change superadmin role")
    new_role = body.get("role", "")
    if new_role not in ("admin", "employee", "owner"):
        raise HTTPException(status_code=422, detail=f"Invalid role: {new_role}")
    sa = resolve_superadmin_user(db, claims)
    old_role = user.role
    user.role = new_role
    _audit_and_commit(
        db, sa,
        "change_user_role",
        target_id=str(user.id),
        details=f"User {user.username}: {old_role} → {new_role}",
    )
    return {"ok": True, "role": new_role}


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
        raise HTTPException(status_code=404, detail="User not found")
    if user.role == "superadmin":
        raise HTTPException(status_code=403, detail="Cannot disable superadmin")
    sa = resolve_superadmin_user(db, claims)
    user.is_active = not user.is_active
    _audit_and_commit(
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
        raise HTTPException(status_code=404, detail="User not found")
    if user.role == "superadmin":
        raise HTTPException(status_code=403, detail="Cannot reset superadmin 2FA via API")
    sa = resolve_superadmin_user(db, claims)
    user.totp_secret = None
    user.totp_enrolled_at = None
    _audit_and_commit(
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
        raise HTTPException(status_code=404, detail="User not found")
    if user.role == "superadmin":
        raise HTTPException(status_code=403, detail="Cannot reset superadmin password via API")
    sa = resolve_superadmin_user(db, claims)
    temp_pw = secrets.token_urlsafe(12)
    user.set_password(temp_pw)
    _audit_and_commit(
        db, sa,
        "force_password_reset",
        target_id=str(user.id),
        details=f"User {user.username}",
    )
    return {"ok": True, "temp_password": temp_pw}


@router.post("/users/{user_id}/revoke-sessions")
def revoke_user_sessions_route(
    user_id: int = Path(..., ge=1),
    db: Session = Depends(get_db),
    claims: dict[str, Any] = Depends(get_principal),
) -> dict[str, Any]:
    """Revoke every active refresh token for a user — they're
    bounced to /login on next API call. Use when: credentials are
    reported compromised, an employee leaves mid-shift, or a stuck
    session needs nuking.

    Sessions for the targeted user only — does NOT touch the
    superadmin's own sessions. Bouncing every store-admin is the
    role-wide revoke path on `PUT /superadmin/permissions`, which
    already exists.
    """
    _require_superadmin(claims)
    from api.Modules.Auth.Models import RefreshToken
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    if user.role == "superadmin":
        raise HTTPException(
            status_code=403,
            detail="Cannot revoke superadmin sessions via API",
        )
    now = utc_now()
    revoked = (
        db.query(RefreshToken)
          .filter(RefreshToken.user_id == user_id)
          .filter(RefreshToken.revoked_at.is_(None))
          .update({"revoked_at": now}, synchronize_session=False)
    )
    sa = resolve_superadmin_user(db, claims)
    _audit_and_commit(
        db, sa, "revoke_user_sessions",
        target_id=str(user.id),
        details=f"User {user.username} ({int(revoked)} tokens revoked)",
    )
    return {"ok": True, "revoked_count": int(revoked)}


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
        raise HTTPException(status_code=404, detail="User not found")
    if user.role == "superadmin":
        raise HTTPException(status_code=403, detail="Cannot impersonate superadmin")
    sa = resolve_superadmin_user(db, claims)
    issuer = JWTIssuer(
        sub=user.id,
        role=user.role or "employee",
        store_id=user.store_id,
        permissions=permissions_for(user.role or "employee", db, store_id=user.store_id),
        full_name=user.full_name or "",
        username=user.username,
    )
    token = issue_access_token(issuer, ttl_seconds=3600)
    _audit_and_commit(
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


# ── Billing overview ────────────────────────────────────────


@router.get("/billing-overview")
def billing_overview_route(
    db: Session = Depends(get_db),
    claims: dict[str, Any] = Depends(get_principal),
) -> dict[str, Any]:
    """Billing health: trials expiring, grace, retention queue,
    recent cancellations, webhook events."""
    _require_superadmin(claims)
    from datetime import datetime, timedelta
    from api.Modules.Billing.Services.trial import get_trial_status
    from api.Modules.Tenancy.Models import Store
    from api.Modules.Webhooks.Models import WebhookEvent

    now = utc_now()
    stores = db.query(Store).all()

    expiring_soon: list[dict[str, Any]] = []
    in_grace: list[dict[str, Any]] = []
    retention_queue: list[dict[str, Any]] = []
    recent_cancels: list[dict[str, Any]] = []

    for s in stores:
        status = get_trial_status(s)
        row = {
            "store_id": s.id, "name": s.name or "", "slug": s.slug or "",
            "plan": s.plan or "", "email": s.email or "",
        }
        if status == "expiring_soon":
            row["trial_ends_at"] = _iso(s.trial_ends_at)
            expiring_soon.append(row)
        elif status == "grace":
            row["grace_ends_at"] = _iso(s.grace_ends_at)
            in_grace.append(row)
        if (s.plan == "inactive" and s.data_retention_until
                and s.data_retention_until > now):
            days_left = (s.data_retention_until - now).days
            row2 = {**row, "data_retention_until": _iso(s.data_retention_until),
                    "days_left": days_left}
            retention_queue.append(row2)
        if s.canceled_at and s.canceled_at >= now - timedelta(days=30):
            row3 = {**row, "canceled_at": _iso(s.canceled_at)}
            recent_cancels.append(row3)

    # Stripe webhook health (7d)
    webhook_stats: dict[str, int] = {}
    try:
        since = now - timedelta(days=7)
        rows = (
            db.query(WebhookEvent.status, func.count(WebhookEvent.id))
            .filter(WebhookEvent.received_at >= since)
            .group_by(WebhookEvent.status)
            .all()
        )
        for st, cnt in rows:
            webhook_stats[st] = cnt
    except Exception:
        pass

    return {
        "expiring_soon": expiring_soon,
        "in_grace": in_grace,
        "retention_queue": retention_queue,
        "recent_cancels": recent_cancels,
        "webhook_stats": webhook_stats,
    }


# ── Email log ──────────────────────────────────────────────


@router.get("/email-log")
def email_log_route(
    q: str | None = Query(None),
    event_type: str | None = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    claims: dict[str, Any] = Depends(get_principal),
) -> dict[str, Any]:
    """Paginated email event log with search + type filter."""
    _require_superadmin(claims)
    from api.Modules.Webhooks.Models import EmailEvent
    from api.Modules.Tenancy.Models import User
    from api.Modules.Superadmin.Repositories import email_events_query

    query = email_events_query(db, search=q, event_type=event_type)
    total = query.count()
    events = (
        query.offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )

    # Suppressed addresses
    suppressed = (
        db.query(User.id, User.username, User.email, User.email_bounced_at)
        .filter(User.email_bounced_at.isnot(None))
        .all()
    )

    rows = []
    for e in events:
        rows.append({
            "id": e.id,
            "to_addr": e.to_addr or "",
            "event_type": e.event_type or "",
            "bounce_type": e.bounce_type or "",
            "message_id": e.message_id or "",
            "created_at": _iso(e.created_at),
        })

    suppressed_rows = [
        {"user_id": u.id, "username": u.username, "email": u.email,
         "bounced_at": _iso(u.email_bounced_at)}
        for u in suppressed
    ]

    return {
        "rows": rows,
        "total": total,
        "page": page,
        "total_pages": ceil(total / per_page),
        "suppressed": suppressed_rows,
    }


# ── Store deep-drill ───────────────────────────────────────


@router.get("/stores/{store_id}/drill")
def store_drill_route(
    store_id: int = Path(..., ge=1),
    db: Session = Depends(get_db),
    claims: dict[str, Any] = Depends(get_principal),
) -> dict[str, Any]:
    """Read-only deep view of a store's data for support."""
    _require_superadmin(claims)
    from datetime import timedelta
    from api.Modules.Billing.Services.trial import get_trial_status
    from api.Modules.Tenancy.Models import Store, StoreEmployee, User
    from api.Modules.Transfers.Models import Transfer

    store = db.get(Store, store_id)
    if store is None:
        raise HTTPException(status_code=404, detail="Store not found")

    # Team
    from api.Modules.Superadmin.Repositories import list_users_in_store
    users = list_users_in_store(db, store_id)
    team = [
        {"id": u.id, "username": u.username, "full_name": u.full_name or "",
         "role": u.role or "", "email": u.email or "",
         "is_active": bool(u.is_active), "has_2fa": bool(u.totp_enrolled_at),
         "last_login_at": _iso(u.last_login_at)}
        for u in users
    ]

    # Employees (roster names)
    employees = (
        db.query(StoreEmployee)
        .filter(StoreEmployee.store_id == store_id)
        .order_by(StoreEmployee.name)
        .all()
    )
    roster = [
        {"id": e.id, "name": e.name or "", "is_active": bool(e.is_active)}
        for e in employees
    ]

    # Recent transfers (last 20)
    recent_transfers = (
        db.query(Transfer)
        .filter(Transfer.store_id == store_id)
        .order_by(Transfer.created_at.desc())
        .limit(20)
        .all()
    )
    transfers = [
        {"id": t.id, "send_date": t.send_date or "",
         "sender_name": t.sender_name or "", "recipient_name": t.recipient_name or "",
         "company": t.company or "", "send_amount": float(t.send_amount or 0),
         "fee": float(t.fee or 0), "total_collected": float(t.total_collected or 0),
         "status": t.status or "", "created_at": _iso(t.created_at)}
        for t in recent_transfers
    ]

    # Transfer stats
    from datetime import datetime
    now = utc_now()
    stats_30d = (
        db.query(
            func.count(Transfer.id),
            func.coalesce(func.sum(Transfer.send_amount), 0.0),
            func.coalesce(func.sum(Transfer.fee), 0.0),
        )
        .filter(
            Transfer.store_id == store_id,
            Transfer.created_at >= now - timedelta(days=30),
            Transfer.status.notin_(["Canceled", "Rejected"]),
        )
        .first()
    )
    transfer_count_30d = stats_30d[0] if stats_30d else 0
    volume_30d = float(stats_30d[1]) if stats_30d else 0.0
    fees_30d = float(stats_30d[2]) if stats_30d else 0.0

    return {
        "store": {
            "id": store.id, "name": store.name or "", "slug": store.slug or "",
            "email": store.email or "", "phone": store.phone or "",
            "address": store.address or "",
            "plan": store.plan or "", "billing_cycle": store.billing_cycle or "",
            "is_active": bool(store.is_active),
            "trial_status": get_trial_status(store),
            "created_at": _iso(store.created_at),
            "trial_ends_at": _iso(store.trial_ends_at),
            "canceled_at": _iso(store.canceled_at),
            "stripe_customer_id": store.stripe_customer_id or "",
        },
        "team": team,
        "roster": roster,
        "recent_transfers": transfers,
        "stats_30d": {
            "transfer_count": transfer_count_30d,
            "volume": volume_30d,
            "fees": fees_30d,
        },
    }


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
    from api.Modules.Superadmin.Repositories import count_all_stores, count_all_users
    total_users = count_all_users(db)
    total_stores = count_all_stores(db)
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
        "server_time": utc_now().isoformat(),
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
    from api.Modules.Superadmin.Repositories import list_all_stores_newest_first
    stores = list_all_stores_newest_first(db)
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
    from api.Modules.Superadmin.Repositories import get_store_by_slug
    if get_store_by_slug(db, slug):
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
    _audit_and_commit(
        db, user, "create_store",
        target_id=str(s.id),
        details=s.slug,
    )
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


# ── Store actions (single + bulk) ──────────────────────────


@router.post("/stores/{store_id}/extend-trial")
def extend_trial_route(
    store_id: int = Path(..., ge=1),
    body: dict[str, Any] = {},
    db: Session = Depends(get_db),
    claims: dict[str, Any] = Depends(get_principal),
) -> dict[str, Any]:
    """Extend a store's trial by N days (default 14)."""
    _require_superadmin(claims)
    from datetime import datetime, timedelta
    from api.Modules.Tenancy.Models import Store
    sa = resolve_superadmin_user(db, claims)
    s = db.get(Store, store_id)
    if s is None:
        raise HTTPException(status_code=404, detail="Store not found")
    days = int(body.get("days", 14))
    if days < 1 or days > 365:
        raise HTTPException(status_code=422, detail="Days must be 1–365")
    base = s.trial_ends_at or utc_now()
    s.trial_ends_at = base + timedelta(days=days)
    if s.grace_ends_at:
        s.grace_ends_at = s.trial_ends_at + timedelta(days=7)
    if s.plan == "inactive":
        s.plan = "trial"
    _audit_and_commit(db, sa, "extend_trial", target_id=str(s.id),
                      details=f"+{days} days → {s.trial_ends_at.isoformat()[:10]}")
    return {"ok": True, "trial_ends_at": s.trial_ends_at.isoformat()}


@router.post("/stores/{store_id}/toggle-active")
def toggle_store_active_route(
    store_id: int = Path(..., ge=1),
    db: Session = Depends(get_db),
    claims: dict[str, Any] = Depends(get_principal),
) -> dict[str, Any]:
    """Enable / disable a store."""
    _require_superadmin(claims)
    from api.Modules.Tenancy.Models import Store
    sa = resolve_superadmin_user(db, claims)
    s = db.get(Store, store_id)
    if s is None:
        raise HTTPException(status_code=404, detail="Store not found")
    s.is_active = not s.is_active
    act = "enable_store" if s.is_active else "disable_store"
    _audit_and_commit(db, sa, act, target_id=str(s.id),
                      details=f"{s.name} ({s.slug})")
    return {"ok": True, "is_active": s.is_active}


@router.get("/retention-dry-run")
def retention_dry_run_route(
    db: Session = Depends(get_db),
    claims: dict[str, Any] = Depends(get_principal),
) -> dict[str, Any]:
    """Preview what `purge_expired_stores` would delete on its
    next run. Read-only, no audit (no mutation).

    Use cases:
      * "did the retention timer get re-stamped by a Stripe retry?"
        verification
      * sanity check before re-enabling the daily purge cron after
        a deploy
      * answering "if I run the cron now, how many stores die"
    """
    _require_superadmin(claims)
    from api.Modules.Billing.Services import retention_purge_dry_run
    return retention_purge_dry_run(db)


@router.post("/stores/{store_id}/clear-retention")
def clear_retention_route(
    store_id: int = Path(..., ge=1),
    db: Session = Depends(get_db),
    claims: dict[str, Any] = Depends(get_principal),
) -> dict[str, Any]:
    """Cancel a store's retention timer so the purge cron will
    leave it alone — does NOT reactivate the Stripe subscription
    (that goes through Checkout). Use when:
      * a stuck `customer.subscription.deleted` retry stamped a
        fresh window on a near-expired store
      * the operator asks for an extension while they decide
        whether to reactivate
      * forensic / support-investigation hold
    """
    _require_superadmin(claims)
    from api.Modules.Billing.Services import clear_cancellation_state
    from api.Modules.Tenancy.Models import Store
    s = db.get(Store, store_id)
    if s is None:
        raise HTTPException(status_code=404, detail="Store not found")
    if s.data_retention_until is None and s.canceled_at is None:
        return {"ok": True, "already_clear": True}
    sa = resolve_superadmin_user(db, claims)
    prior = (
        s.data_retention_until.isoformat()
        if s.data_retention_until else "(none)"
    )
    clear_cancellation_state(s)
    _audit_and_commit(
        db, sa, "clear_retention",
        target_id=str(s.id),
        details=f"prior retention_until={prior}",
    )
    return {"ok": True}


@router.post("/bulk-action")
def bulk_action_route(
    body: dict[str, Any],
    db: Session = Depends(get_db),
    claims: dict[str, Any] = Depends(get_principal),
) -> dict[str, Any]:
    """Bulk action on multiple stores. Actions: extend_trial,
    enable, disable."""
    _require_superadmin(claims)
    from datetime import datetime, timedelta
    from api.Modules.Tenancy.Models import Store
    sa = resolve_superadmin_user(db, claims)
    store_ids = body.get("store_ids", [])
    action = body.get("action", "")
    if not store_ids or not isinstance(store_ids, list):
        raise HTTPException(status_code=422, detail="store_ids must be a non-empty list")
    if action not in ("extend_trial", "enable", "disable"):
        raise HTTPException(status_code=422, detail=f"Invalid action: {action}")

    from api.Modules.Superadmin.Repositories import list_stores_by_ids
    stores = list_stores_by_ids(db, store_ids)
    if not stores:
        raise HTTPException(status_code=404, detail="No stores found")

    results = []
    for s in stores:
        if action == "extend_trial":
            days = int(body.get("days", 14))
            base = s.trial_ends_at or utc_now()
            s.trial_ends_at = base + timedelta(days=days)
            if s.grace_ends_at:
                s.grace_ends_at = s.trial_ends_at + timedelta(days=7)
            if s.plan == "inactive":
                s.plan = "trial"
            results.append({"store_id": s.id, "name": s.name,
                           "trial_ends_at": s.trial_ends_at.isoformat()})
        elif action == "enable":
            s.is_active = True
            results.append({"store_id": s.id, "name": s.name, "is_active": True})
        elif action == "disable":
            s.is_active = False
            results.append({"store_id": s.id, "name": s.name, "is_active": False})

    _audit_and_commit(db, sa, f"bulk_{action}",
                      target_id=",".join(str(s.id) for s in stores),
                      details=f"{len(stores)} stores")
    return {"ok": True, "count": len(stores), "results": results}


# ── Store account credit (Stripe balance) ──────────────────


@router.post(
    "/stores/{store_id}/credit",
    response_model=SuperadminStoreCreditResponse,
)
def credit_store_route(
    body: SuperadminStoreCreditRequest,
    store_id: int = Path(..., ge=1),
    db: Session = Depends(get_db),
    claims: dict[str, Any] = Depends(get_principal),
) -> SuperadminStoreCreditResponse:
    """Issue a goodwill credit to a store's Stripe customer balance.

    The credit lands on the Stripe customer balance and Stripe applies
    it to the store's next invoice automatically. Use for make-goods:
    downtime compensation, a billing dispute, or a promised discount
    that never made it onto an invoice.

    Same Stripe primitive as the referral-credit path
    (``create_balance_transaction`` with a negative amount) but this is
    an interactive action, so failures surface instead of being
    swallowed:
      422 — amount outside the guardrail range (1..500000 cents).
      409 — store has no Stripe customer (put it on a plan first).
      503 — Stripe isn't configured (operator must set STRIPE_SECRET_KEY).
      502 — Stripe returned an error.

    Per CLAUDE.md invariant #7 the credit records an audit row; the
    Stripe call happens first, then the audit + commit are atomic on
    our side (a post-credit commit failure leaves the credit posted
    but that's inherent to any external side-effect — the exception
    surfaces it)."""
    _require_superadmin(claims)
    from api.Modules.Billing.Services import (
        InvalidCreditAmountError,
        NoBillingCustomerError,
        StripeServiceError,
        issue_store_credit,
    )
    from api.Modules.Billing.Services.config import StripeNotConfiguredError
    from api.Modules.Tenancy.Models import Store
    s = db.get(Store, store_id)
    if s is None:
        raise HTTPException(status_code=404, detail="Store not found")
    sa = resolve_superadmin_user(db, claims)
    try:
        txn_id = issue_store_credit(
            db, s, body.amount_cents,
            reason=body.reason,
            superadmin_username=sa.username or "",
        )
    except InvalidCreditAmountError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except StripeNotConfiguredError:
        raise HTTPException(
            status_code=503,
            detail=(
                "Billing isn't configured on this server yet. "
                "An administrator needs to set STRIPE_SECRET_KEY before "
                "credits can be issued."
            ),
        )
    except NoBillingCustomerError:
        raise HTTPException(
            status_code=409,
            detail=(
                "This store has no Stripe billing account. "
                "Put it on a paid plan before issuing a credit."
            ),
        )
    except StripeServiceError:
        raise HTTPException(
            status_code=502,
            detail="Stripe rejected the credit. Please try again.",
        )
    dollars = body.amount_cents / 100
    _audit_and_commit(
        db, sa, "credit_store",
        target_id=str(s.id),
        details=(
            f"${dollars:,.2f} credit "
            f"(txn={txn_id or 'n/a'})"
            + (f" — {body.reason[:80]}" if body.reason.strip() else "")
        ),
    )
    return SuperadminStoreCreditResponse(
        ok=True, amount_cents=body.amount_cents, stripe_txn_id=txn_id,
    )


# ── Store communication ─────────────────────────────────────


@router.post("/stores/{store_id}/email")
def email_store_route(
    store_id: int = Path(..., ge=1),
    body: dict[str, Any] = {},
    db: Session = Depends(get_db),
    claims: dict[str, Any] = Depends(get_principal),
) -> dict[str, Any]:
    """Send an email to a store's admin(s)."""
    _require_superadmin(claims)
    from api.Modules.Notifications.Services.smtp import send_email
    from api.Modules.Tenancy.Models import Store, User
    sa = resolve_superadmin_user(db, claims)
    store = db.get(Store, store_id)
    if store is None:
        raise HTTPException(status_code=404, detail="Store not found")
    subject = body.get("subject", "").strip()
    message = body.get("message", "").strip()
    if not subject or not message:
        raise HTTPException(status_code=422, detail="Subject and message are required")
    from api.Modules.Superadmin.Repositories import list_active_admins_for_store
    admins = list_active_admins_for_store(db, store_id)
    recipients = [u for u in admins if u.email]
    if not recipients:
        raise HTTPException(status_code=422, detail="No admin with an email address found for this store")
    sent_to = []
    for u in recipients:
        ok = send_email(db, u.email, subject, message)
        if ok:
            sent_to.append(u.email)
    _audit_and_commit(db, sa, "email_store", target_id=str(store_id),
                      details=f"Subject: {subject[:60]} → {len(sent_to)} recipient(s)")
    return {"ok": True, "sent_to": sent_to, "total": len(sent_to)}


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
    from api.Modules.Superadmin.Repositories import superadmin_audit_query
    q = superadmin_audit_query(db, action=action)
    total = q.count()
    rows = (
        q.offset((page - 1) * per_page)
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
    from api.Modules.Superadmin.Repositories import list_discount_codes
    rows = list_discount_codes(db)
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
    from api.Modules.Superadmin.Repositories import get_discount_code
    d = get_discount_code(db, discount_id)
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


# ── Per-store permission overrides (from store drill) ──────


@router.get("/stores/{store_id}/permissions")
def superadmin_store_permissions_route(
    store_id: int = Path(..., ge=1),
    db: Session = Depends(get_db),
    claims: dict[str, Any] = Depends(get_principal),
) -> dict:
    """Permission matrix for a specific store. Superadmin can see
    and edit admin + employee roles."""
    _require_superadmin(claims)
    from api.Modules.Tenancy.Models import Store
    store = db.get(Store, store_id)
    if not store:
        raise HTTPException(status_code=404, detail="Store not found")

    from api.Core.Permissions import get_permission_matrix
    visible_roles = ["admin", "employee"]
    editable_roles = ["admin", "employee"]
    result = get_permission_matrix(store_id, visible_roles, editable_roles)
    result["store_name"] = store.name or ""
    return result


@router.put("/stores/{store_id}/permissions")
def superadmin_update_store_permissions_route(
    store_id: int = Path(..., ge=1),
    body: dict = ...,
    db: Session = Depends(get_db),
    claims: dict[str, Any] = Depends(get_principal),
) -> dict:
    """Update per-store permission overrides. Superadmin can edit
    admin + employee roles."""
    _require_superadmin(claims)
    from api.Modules.Tenancy.Models import Store
    store = db.get(Store, store_id)
    if not store:
        raise HTTPException(status_code=404, detail="Store not found")

    from api.Core.Permissions import (
        get_permission_matrix, set_store_permissions,
        RBAC_RESOURCES, RBAC_ACTIONS,
    )
    editable_roles = ["admin", "employee"]

    matrix = body.get("matrix", {})
    changes = body.get("changes", [])
    affected_roles: set[str] = set()

    if matrix:
        for role, resources in matrix.items():
            if role not in editable_roles:
                continue
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
        for role in affected_roles:
            set_store_permissions(store_id, role, current_matrix[role])

    if affected_roles:
        sa = resolve_superadmin_user(db, claims)
        _audit_store(
            db, sa,
            "update_store_permissions",
            target_id=str(store_id),
            details=f"superadmin updated permissions for store '{store.name}'",
        )
        from api.Modules.Auth.Services.principal import invalidate_sessions_for_role
        for r in affected_roles:
            invalidate_sessions_for_role(db, store_id, r)
    db.commit()
    return superadmin_store_permissions_route(
        store_id=store_id, db=db, claims=claims,
    )


@router.post("/stores/{store_id}/permissions/reset")
def superadmin_reset_store_permissions_route(
    store_id: int = Path(..., ge=1),
    body: dict = ...,
    db: Session = Depends(get_db),
    claims: dict[str, Any] = Depends(get_principal),
) -> dict:
    """Reset a role's per-store overrides to global defaults."""
    _require_superadmin(claims)
    from api.Modules.Tenancy.Models import Store
    store = db.get(Store, store_id)
    if not store:
        raise HTTPException(status_code=404, detail="Store not found")
    target_role = body.get("role", "")
    if target_role not in ["admin", "employee"]:
        raise HTTPException(status_code=403, detail=f"Cannot reset {target_role} permissions")
    from api.Core.Permissions import reset_store_to_defaults
    reset_store_to_defaults(store_id, target_role)
    sa = resolve_superadmin_user(db, claims)
    _audit_store(
        db, sa,
        "reset_store_permissions",
        target_id=str(store_id),
        details=f"superadmin reset {target_role} permissions to global defaults for store '{store.name}'",
    )
    from api.Modules.Auth.Services.principal import invalidate_sessions_for_role
    invalidate_sessions_for_role(db, store_id, target_role)
    db.commit()
    return superadmin_store_permissions_route(
        store_id=store_id, db=db, claims=claims,
    )

