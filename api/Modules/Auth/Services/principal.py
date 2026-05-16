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


def resolve_superadmin_user(db: Session, claims: dict) -> User:
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
