"""Password-flow login Service.

Authenticates `(store_id, username, password)` against the DB and
returns a `LoginResult` carrying a JWT access token + minimal user
metadata. Per the ADR JWT-claims model, the full permission set is
embedded as a claim at issue time so subsequent requests don't have
to re-fetch on every hit.

What this Service deliberately does NOT do (yet):
- TOTP / passkey verification (PR 20+).
- Refresh tokens / rotation (follow-up PR after the Controller lands).
- Audit logging — the legacy login route handles that today; we'll
  port it once the Controller wraps the Service.
"""
from dataclasses import dataclass

from sqlalchemy.orm import Session

from api.Modules.Auth.Models import User
from api.Modules.Auth.Repositories import find_user_by_username_in_store
from api.Modules.Auth.Services.jwt_issuer import (
    JWTIssuer,
    issue_access_token,
)


# Permissions per role. Embedded as JWT claims so subsequent FastAPI
# requests can authorize without re-hitting the DB. Mirrors the role
# checks that gate the legacy Flask routes (login_required,
# admin_required, owner_required, superadmin_required).
_ROLE_PERMISSIONS: dict[str, list[str]] = {
    "superadmin": [
        "platform.admin",
        "store.admin",
        "store.employee",
        "owner.read",
    ],
    "owner": [
        "owner.read",
        "owner.admin",
    ],
    "admin": [
        "store.admin",
        "store.employee",
    ],
    "employee": [
        "store.employee",
    ],
}


def permissions_for(role: str) -> list[str]:
    """The permission claim list for a given role. Unknown roles get
    no permissions — defensive against a role that's not in the
    matrix yet (e.g. a future "viewer" tier)."""
    return list(_ROLE_PERMISSIONS.get(role, []))


@dataclass
class LoginResult:
    """Successful-login payload. The `access_token` is the JWT the
    Controller hands back to the client; everything else is summary
    info the React frontend uses to render the user chrome without
    a separate /me roundtrip on first paint."""
    access_token: str
    user_id: int
    role: str
    store_id: int | None
    username: str
    full_name: str
    permissions: list[str]


class AuthenticationError(Exception):
    """Raised when credentials are invalid OR the user is disabled.
    Same exception type for both cases so the Controller can return
    the same opaque "Invalid username or password" 401 — never leak
    "user exists but is disabled" via the response shape."""


def authenticate_password(
    db: Session, *, store_id: int | None, username: str, password: str,
) -> LoginResult:
    """Verify `(store_id, username, password)` and return a JWT-bearing
    `LoginResult`. Raises `AuthenticationError` on any failure path.

    `store_id=None` is the superadmin scope (`User.store_id IS NULL`).
    """
    user = find_user_by_username_in_store(db, store_id, username)
    if user is None or not user.check_password(password):
        raise AuthenticationError("Invalid username or password")
    if not user.is_active:
        raise AuthenticationError("Invalid username or password")

    perms = permissions_for(user.role)
    issuer = JWTIssuer(
        sub=user.id,
        role=user.role,
        store_id=user.store_id,
        permissions=perms,
        full_name=user.full_name or "",
        username=user.username,
    )
    token = issue_access_token(issuer)
    return LoginResult(
        access_token=token,
        user_id=user.id,
        role=user.role,
        store_id=user.store_id,
        username=user.username,
        full_name=user.full_name or "",
        permissions=perms,
    )
