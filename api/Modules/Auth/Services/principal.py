"""Principal-resolution helpers shared across the FastAPI controllers.

``get_principal`` (in ``api.Modules.Auth.Controllers``) returns the
decoded JWT claims dict; these helpers take that dict + a session
and return the canonical ``User`` row when needed for audit /
mutation paths.

Lives in Auth/Services rather than Auth/Controllers because it's
called from non-Auth modules (Announcements, FeatureFlags,
Superadmin) and importing controllers from controllers makes the
dependency graph harder to reason about. Services are import-safe
from anywhere.
"""
from fastapi import HTTPException
from sqlalchemy.orm import Session

from api.Modules.Auth.Models import User
from typing import Any
from api.Core.Clock import utc_now


def resolve_store_scope(claims: dict[str, Any]) -> int:
    """Extract the JWT principal's `store_id`, or 403.

    Used by the Admin / Monthly / BankSync controllers (and any
    other module gated on "you must be signed in to a specific
    store"). The detail message is intentionally generic — the
    SPA route the user is on supplies the page-specific context
    in its empty state.
    """
    sid = claims.get("store_id")
    if sid is None:
        role = claims.get("role", "")
        if role == "owner":
            detail = (
                "This endpoint requires a store scope. "
                "Use the /owner/* endpoints instead."
            )
        else:
            detail = (
                "JWT does not carry a store scope. "
                "Sign in to a specific store first."
            )
        raise HTTPException(status_code=403, detail=detail)
    return int(sid)


def resolve_superadmin_user(db: Session, claims: dict[str, Any]) -> User:
    """Resolve JWT claims → ``User`` row, gated on role=superadmin.

    Used by the mutation endpoints across the Superadmin /
    Announcements / FeatureFlags modules so the audit trail can
    stamp ``admin_id`` + ``admin_name`` from canonical DB values
    (not whatever the JWT happens to carry). Read-only superadmin
    endpoints continue to call the cheaper claim-only guard
    (``role == "superadmin"``) since they don't audit.

    Raises 403 when the principal isn't a superadmin, 401 when
    the JWT subject is missing or doesn't resolve to a User row.
    """
    if claims.get("role") != "superadmin":
        raise HTTPException(
            status_code=403, detail="Superadmin scope required.",
        )
    sub = claims.get("sub")
    if sub is None:
        raise HTTPException(
            status_code=401, detail="JWT is missing the subject claim.",
        )
    user = db.get(User, int(sub))
    if user is None:
        raise HTTPException(
            status_code=401,
            detail="JWT subject does not resolve to a user.",
        )
    return user


def has_permission(claims: dict[str, Any], resource: str, action: str) -> bool:
    """Live permission check via Casbin. Permission changes take
    effect immediately — no JWT refresh needed."""
    if claims.get("role") == "superadmin":
        return True
    from api.Core.Permissions import check_permission
    return check_permission(
        claims.get("role", ""), claims.get("store_id"), resource, action,
    )


def require_permission(
    claims: dict[str, Any], resource: str, action: str,
) -> None:
    """Raise 403 if the principal lacks permission (live Casbin check)."""
    if not has_permission(claims, resource, action):
        raise HTTPException(
            status_code=403,
            detail=f"Missing permission: {resource}.{action}",
        )


def invalidate_sessions_for_role(db: Session, store_id: int, role: str) -> None:
    """Revoke active refresh tokens for all users of a given role at a
    store. Forces re-login so fresh permissions take effect immediately
    instead of waiting up to 30 minutes for the access token to expire."""
    from api.Modules.Auth.Models import RefreshToken
    now = utc_now()
    db.query(RefreshToken).filter(
        RefreshToken.user_id.in_(
            db.query(User.id).filter(
                User.store_id == store_id,
                User.role == role,
                User.is_active.is_(True),
            )
        ),
        RefreshToken.revoked_at.is_(None),
        RefreshToken.expires_at > now,
    ).update({"revoked_at": now}, synchronize_session="fetch")
    db.flush()
