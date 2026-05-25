"""Password-flow login Service.

Authenticates `(store_id, username, password)` against the DB and
returns either a `LoginResult` carrying a full JWT (no 2FA needed)
or a `LoginPendingResult` carrying a short-lived "pending" token
(2FA must be cleared via `/auth/login/totp` or
`/auth/login/recovery` before the caller gets a real access token).

Per the ADR JWT-claims model, the full permission set is embedded
as a claim at issue time so subsequent requests don't have to
re-fetch on every hit.

What this Service deliberately does NOT do (yet):
- Passkey verification (separate PR — needs WebAuthn challenge plumbing).
- Refresh tokens / rotation (follow-up PR after the Controller lands).
- Audit logging — the legacy login route handles that today; we'll
  port it once the Controller wraps the Service.
"""
from dataclasses import dataclass

from sqlalchemy.orm import Session

from api.Modules.Auth.Models import User
from api.Modules.Auth.Repositories import (
    find_user_by_username,
    find_user_by_username_in_store,
)
from api.Modules.Auth.Services.jwt_issuer import (
    JWTIssuer,
    issue_access_token,
    issue_pending_2fa_token,
)
from api.Modules.Auth.Services.totp import (
    is_enrolled,
    needs_totp,
)
from typing import Any


# Permissions per role. Embedded as JWT claims so subsequent
# requests can authorize without re-hitting the DB.
# Legacy coarse-grained permissions — still emitted alongside the
# granular resource.action permissions so existing JWT checks don't
# break during the incremental migration.
_LEGACY_ROLE_PERMISSIONS: dict[str, list[str]] = {
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

# Granular RBAC resources and actions. Superadmin edits these via
# /app/superadmin/permissions. Each (role, resource, action) tuple
# stored in the role_permission table means "allowed".
RBAC_RESOURCES = [
    "transfers", "customers", "daily_book", "monthly",
    "batches", "bank_sync", "reports", "settings",
    "users", "time_clock", "return_checks",
]
RBAC_ACTIONS = ["create", "read", "update", "delete"]

# Default grants seeded on first boot. Superadmin gets everything
# implicitly (not stored). Owner gets read on most store resources.
RBAC_DEFAULTS: dict[str, list[str]] = {
    "admin": [
        f"{r}.{a}" for r in RBAC_RESOURCES for a in RBAC_ACTIONS
    ],
    "employee": [
        "transfers.create", "transfers.read", "transfers.update",
        "customers.create", "customers.read", "customers.update",
        "daily_book.read",
        "time_clock.create", "time_clock.read",
        "return_checks.read",
    ],
    "owner": [
        f"{r}.read" for r in RBAC_RESOURCES
    ] + [
        "settings.update",
    ],
}


def seed_rbac_defaults(db: "Session") -> None:
    """Insert default RBAC rows if the table is empty. Called from
    init_db() on boot — idempotent."""
    from api.Modules.Auth.Models import RolePermission
    if db.query(RolePermission).first() is not None:
        return
    for role, perms in RBAC_DEFAULTS.items():
        for perm in perms:
            resource, action = perm.split(".", 1)
            db.add(RolePermission(role=role, resource=resource, action=action))
    db.commit()


def permissions_for(role: str, db: "Session | None" = None) -> list[str]:
    """The permission claim list for a given role.

    Reads granular permissions from the DB when a session is provided,
    falling back to RBAC_DEFAULTS if the table is empty or unavailable.
    Always includes the legacy coarse-grained permissions for backward
    compatibility. Superadmin gets everything."""
    legacy = list(_LEGACY_ROLE_PERMISSIONS.get(role, []))
    if role == "superadmin":
        all_granular = [f"{r}.{a}" for r in RBAC_RESOURCES for a in RBAC_ACTIONS]
        return legacy + all_granular
    granular: list[str] = []
    if db is not None:
        try:
            from api.Modules.Auth.Models import RolePermission
            rows = (
                db.query(RolePermission.resource, RolePermission.action)
                .filter(RolePermission.role == role)
                .all()
            )
            granular = [f"{r}.{a}" for r, a in rows]
        except Exception:
            pass
    if not granular:
        granular = list(RBAC_DEFAULTS.get(role, []))
    return legacy + granular


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


@dataclass
class LoginPendingResult:
    """Returned in place of a `LoginResult` when password auth
    succeeds but the user must clear a second factor before getting
    a real access token. Carries a short-lived JWT (5min, purpose=
    "totp-pending") that the SPA exchanges via `/auth/login/totp`,
    `/auth/login/recovery`, or — when `enroll_required=True` — the
    `/auth/login/totp/enroll/*` set."""
    pending_token: str
    user_id: int
    has_recovery_codes: bool
    enroll_required: bool = False


class AuthenticationError(Exception):
    """Raised when credentials are invalid OR the user is disabled.
    Same exception type for both cases so the Controller can return
    the same opaque "Invalid username or password" 401 — never leak
    "user exists but is disabled" via the response shape."""


class TotpEnrollmentRequired(Exception):
    """Raised when password auth succeeds but the user must enroll
    a TOTP factor before logging in (e.g. fresh superadmin). The
    SPA can't drive the QR-code enrollment flow yet; we tell the
    user to complete enrollment via the legacy site."""


def _issue_full_login(user: User, db: "Session | None" = None) -> LoginResult:
    perms = permissions_for(user.role, db)
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


def _maybe_pending_2fa(db: Session, user: User) -> LoginPendingResult | None:
    """If `user` is in a TOTP-required role, gate the login behind
    the 2FA hop. Returns a pending result, or None if no 2FA hop is
    needed (caller mints a full access token).

    Two pending shapes:
    - `enroll_required=False` (already enrolled) — SPA goes to
      /app/login/2fa to enter a code or recovery code.
    - `enroll_required=True` (role requires TOTP, no secret yet) —
      SPA goes to /app/login/2fa/enroll to mint a secret + scan QR.
    """
    if not needs_totp(user):
        return None
    from api.Modules.Auth.Models import RecoveryCode
    if not is_enrolled(user):
        return LoginPendingResult(
            pending_token=issue_pending_2fa_token(user.id),
            user_id=user.id,
            has_recovery_codes=False,
            enroll_required=True,
        )
    has_recovery = (
        db.query(RecoveryCode)
          .filter_by(user_id=user.id, used_at=None)
          .first()
        is not None
    )
    return LoginPendingResult(
        pending_token=issue_pending_2fa_token(user.id),
        user_id=user.id,
        has_recovery_codes=has_recovery,
    )


def authenticate_password(
    db: Session, *, store_id: int | None, username: str, password: str,
) -> LoginResult | LoginPendingResult:
    """Verify `(store_id, username, password)`. Returns either:
      - `LoginResult` carrying a full access token (no 2FA needed), OR
      - `LoginPendingResult` carrying a 2FA-pending token (the caller
        must clear the second factor via `/auth/login/totp` or
        `/auth/login/recovery` to upgrade).

    Raises `AuthenticationError` on bad credentials / disabled user,
    or `TotpEnrollmentRequired` if the role requires TOTP but the
    user hasn't enrolled yet.

    `store_id=None` is the superadmin scope (`User.store_id IS NULL`).
    """
    user = find_user_by_username_in_store(db, store_id, username)
    if user is None or not user.check_password(password):
        raise AuthenticationError("Invalid username or password")
    if not user.is_active:
        raise AuthenticationError("Invalid username or password")

    pending = _maybe_pending_2fa(db, user)
    if pending is not None:
        return pending
    return _issue_full_login(user)


def authenticate_password_cross_store(
    db: Session, *, username: str, password: str,
) -> LoginResult | LoginPendingResult:
    """Cross-store JWT login for the SPA. Same shape as
    `authenticate_password` but does NOT require `store_id` — the
    user's home store is looked up by username across all stores
    (first match wins, like the legacy `/login` POST).

    Returns either a full `LoginResult` or a `LoginPendingResult`
    (when the user's role requires 2FA — see `authenticate_password`).

    Raises `AuthenticationError` on bad credentials / disabled
    user, or `TotpEnrollmentRequired` if 2FA is required but
    enrollment is incomplete.

    Employees are intentionally rejected here because the legacy
    flow does the same: an employee on the cookieless landing
    page is told to use their store's slug-scoped page.
    """
    user = verify_password_cross_store(db, username, password)
    if user is None:
        raise AuthenticationError("Invalid username or password")
    if user.role == "employee":
        # Same behavior as the legacy /login route — employees
        # must sign in via their store's slug-scoped page.
        raise AuthenticationError(
            "Please use your store's sign-in page",
        )

    pending = _maybe_pending_2fa(db, user)
    if pending is not None:
        return pending
    return _issue_full_login(user)


def finalize_2fa_with_totp(
    db: Session, *, pending_token: str, code: str,
) -> LoginResult:
    """Exchange a 2FA-pending token + TOTP code for a full access
    token. Raises `AuthenticationError` on a bad / expired pending
    token, a missing user, or an invalid code.

    Caller is responsible for committing — TOTP verify is a pure
    read so we don't strictly need a commit, but the symmetric
    `finalize_2fa_with_recovery_code` (below) needs one to mark
    the recovery code consumed, and exposing both helpers with
    the same call shape keeps the Controller path simple.
    """
    import jwt as _jwt  # local import to keep the type annotation clean
    from api.Modules.Auth.Services.jwt_issuer import decode_pending_2fa_token
    from api.Modules.Auth.Services.totp import verify_totp_token

    try:
        claims = decode_pending_2fa_token(pending_token)
    except _jwt.InvalidTokenError as exc:
        raise AuthenticationError(str(exc) or "Invalid pending token")
    user = db.get(User, int(claims["sub"]))
    if user is None or not user.is_active:
        raise AuthenticationError("Invalid or expired pending session")
    if not verify_totp_token(user, code):
        raise AuthenticationError("Invalid verification code")
    return _issue_full_login(user)


def _user_for_pending(db: Session, pending_token: str) -> User:
    """Resolve a pending-2FA token to its User. Raises
    `AuthenticationError` on bad/expired tokens or missing/disabled
    users. Used by both the verify path (TOTP / recovery) and the
    enrollment path so token semantics stay consistent."""
    import jwt as _jwt
    from api.Modules.Auth.Services.jwt_issuer import decode_pending_2fa_token

    try:
        claims = decode_pending_2fa_token(pending_token)
    except _jwt.InvalidTokenError as exc:
        raise AuthenticationError(str(exc) or "Invalid pending token")
    user = db.get(User, int(claims["sub"]))
    if user is None or not user.is_active:
        raise AuthenticationError("Invalid or expired pending session")
    return user


def start_totp_enrollment(
    db: Session, *, pending_token: str,
) -> dict[str, Any]:
    """Mint a TOTP secret for `user` (if none pending) and return the
    payload the SPA renders on its enrollment page: QR SVG, raw
    secret, secret split into 4-char chunks, username, issuer.

    Refreshes reuse the pending secret so a user who already scanned
    the QR doesn't have to start over. Caller commits.
    """
    import io
    import pyotp
    import qrcode
    import qrcode.image.svg
    from api.Modules.Auth.Services.totp import needs_totp

    user = _user_for_pending(db, pending_token)
    if not needs_totp(user):
        raise AuthenticationError("This account doesn't use 2FA")
    if not user.totp_secret:
        user.totp_secret = pyotp.random_base32()
        db.flush()
    issuer = "DineroBook"
    uri = pyotp.totp.TOTP(user.totp_secret).provisioning_uri(
        name=user.username, issuer_name=issuer,
    )
    img = qrcode.make(
        uri, image_factory=qrcode.image.svg.SvgPathImage,
        box_size=8, border=2,
    )
    buf = io.BytesIO()
    img.save(buf)
    qr_svg = buf.getvalue().decode("utf-8")
    chunks = " ".join(
        user.totp_secret[i:i + 4]
        for i in range(0, len(user.totp_secret), 4)
    )
    return {
        "qr_svg": qr_svg, "secret": user.totp_secret,
        "secret_chunks": chunks, "username": user.username,
        "issuer": issuer,
    }


def finish_totp_enrollment(
    db: Session, *, pending_token: str, code: str,
) -> list[str]:
    """Verify the user's first 6-digit code, mark enrollment
    complete (`totp_enrolled_at`), generate one-shot recovery codes
    and return them in plaintext. The caller MUST hold the codes
    in component state — they are not retrievable later. Raises
    `AuthenticationError` on bad/expired tokens or invalid codes.
    Caller commits.
    """
    from datetime import datetime
    from api.Modules.Auth.Services.totp import (
        generate_recovery_codes, verify_totp_token,
    )

    user = _user_for_pending(db, pending_token)
    if not user.totp_secret:
        raise AuthenticationError(
            "Enrollment hasn't started — call /enroll/start first.",
        )
    if not verify_totp_token(user, code):
        raise AuthenticationError("Invalid verification code")
    user.totp_enrolled_at = datetime.utcnow()
    return generate_recovery_codes(db, user)


def confirm_recovery_codes_saved(
    db: Session, *, pending_token: str,
) -> LoginResult:
    """Finalise the post-enrollment login. The user has confirmed
    they saved their recovery codes; we exchange the still-valid
    pending token for a real access token. Raises
    `AuthenticationError` on a bad/expired pending token, or when
    the user hasn't actually completed enrollment yet."""
    from api.Modules.Auth.Services.totp import is_enrolled

    user = _user_for_pending(db, pending_token)
    if not is_enrolled(user):
        raise AuthenticationError(
            "Enrollment is not complete — verify a code first.",
        )
    return _issue_full_login(user)


def finalize_2fa_with_recovery_code(
    db: Session, *, pending_token: str, code: str,
) -> LoginResult:
    """Exchange a 2FA-pending token + single-use recovery code for
    a full access token. Marks the recovery code consumed.
    Raises `AuthenticationError` on a bad / expired pending token,
    a missing user, or an unrecognized recovery code.

    Caller commits — the recovery code's `used_at` flush isn't
    durable until the session commits.
    """
    import jwt as _jwt
    from api.Modules.Auth.Services.jwt_issuer import decode_pending_2fa_token
    from api.Modules.Auth.Services.totp import consume_recovery_code

    try:
        claims = decode_pending_2fa_token(pending_token)
    except _jwt.InvalidTokenError as exc:
        raise AuthenticationError(str(exc) or "Invalid pending token")
    user = db.get(User, int(claims["sub"]))
    if user is None or not user.is_active:
        raise AuthenticationError("Invalid or expired pending session")
    if not consume_recovery_code(db, user, code):
        raise AuthenticationError("Invalid recovery code")
    return _issue_full_login(user)


def verify_password_cross_store(
    db: Session, username: str, password: str,
) -> User | None:
    """Cross-store credential check used by the bare ``/login``
    page (which doesn't know which store the user belongs to — it
    picks the first matching username). Returns the User row when
    creds + is_active pass; ``None`` otherwise.

    Distinct from `authenticate_password`:
    - takes only username + password (no store_id)
    - returns the SQLAlchemy User row (Flask needs it for the TOTP
      routing logic + session establishment), not a JWT-bearing
      LoginResult
    - returns None on failure instead of raising — Flask renders an
      inline error string, doesn't translate to HTTP

    This is a transitional helper. Once the Auth Flask flip
    completes (Flask login HTML → React login form → /api/v2/auth/login),
    this can be deleted; the React app will use the JWT-emitting
    `authenticate_password` directly.
    """
    if not username or not password:
        return None
    user = find_user_by_username(db, username)
    if user is None or not user.is_active:
        return None
    if not user.check_password(password):
        return None
    return user
