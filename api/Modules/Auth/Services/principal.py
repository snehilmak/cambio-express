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
        raise HTTPException(
            status_code=403,
            detail=(
                "JWT does not carry a store scope. Sign in as a "
                "store admin or owner."
            ),
        )
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
    """Check if the JWT principal has a specific granular permission.

    Superadmin always returns True. For other roles, checks the
    ``perms`` claim list for ``resource.action``."""
    if claims.get("role") == "superadmin":
        return True
    perms = claims.get("perms", [])
    return f"{resource}.{action}" in perms


def require_permission(
    claims: dict[str, Any], resource: str, action: str,
) -> None:
    """Raise 403 if the JWT principal lacks a specific permission.

    Use this in controllers to gate endpoints by permission instead
    of role. Superadmin always passes."""
    if not has_permission(claims, resource, action):
        raise HTTPException(
            status_code=403,
            detail=f"Missing permission: {resource}.{action}",
        )
