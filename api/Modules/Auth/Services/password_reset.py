"""Password-reset token Service.

Token-side of the password-reset flow. The Controller routes glue
email sending + response rendering onto these helpers; the Service
stays HTTP-agnostic so it can be exercised directly by unit tests.

Tokens are stored as `sha256(raw_hex)` so the raw token never sits
in the DB. Single-use, default 1-hour expiry per CLAUDE.md
invariant #10. Superadmin is intentionally excluded — recovery for
that role goes through `flask reset-superadmin`.
"""
import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from api.Modules.Auth.Models import PasswordResetToken, User


# Default expiry window. The legacy module-level constant is
# `PASSWORD_RESET_TTL_HOURS = 1`; mirroring it here keeps the
# Service self-contained and avoids circular imports with app.py.
DEFAULT_TTL_HOURS = 1

# Roles eligible for the email-based reset flow. Employees and
# superadmins are deliberately excluded:
# - Employees: ask their store admin (admin_reset_employee_password)
# - Superadmins: 2FA bypass risk; reset via `flask reset-superadmin`
_ELIGIBLE_ROLES = ("admin", "owner")


@dataclass
class IssuedToken:
    """Successful issue payload. The Flask route uses `user` to
    build the email + the `raw_token` to embed in the reset URL."""
    user: User
    raw_token: str


def hash_token(raw: str) -> str:
    """sha256 hex — matches the legacy column size + format. Public
    so other modules can compare hashes without round-tripping the
    raw token."""
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def issue_password_reset_token(
    db: Session, username: str,
    *, ttl_hours: int = DEFAULT_TTL_HOURS,
) -> IssuedToken | None:
    """Mint a fresh reset token for a user identified by username.

    Returns the (user, raw_token) pair on success. Returns None when:
      - username is empty / None
      - no User matches
      - the matching User isn't in the eligible role list
      - the matching User is inactive

    On success, also invalidates any still-valid existing tokens for
    that user so the prior link in their inbox stops working.

    Caller is responsible for committing the surrounding transaction.
    """
    norm = (username or "").strip().lower()
    if not norm:
        return None

    user = (
        db.query(User)
          .filter(User.username == norm)
          .filter(User.role.in_(_ELIGIBLE_ROLES))
          .first()
    )
    if user is None or not user.is_active:
        return None

    now = datetime.utcnow()
    # Invalidate any still-valid tokens for this user (race-prevention
    # against an attacker who already has a stale link).
    (
        db.query(PasswordResetToken)
          .filter(
              PasswordResetToken.user_id == user.id,
              PasswordResetToken.used_at.is_(None),
              PasswordResetToken.expires_at > now,
          )
          .update({"used_at": now}, synchronize_session=False)
    )
    raw = secrets.token_urlsafe(48)
    db.add(PasswordResetToken(
        user_id=user.id, token_hash=hash_token(raw),
        expires_at=now + timedelta(hours=ttl_hours),
    ))
    db.flush()
    return IssuedToken(user=user, raw_token=raw)


def verify_password_reset_token(
    db: Session, raw_token: str,
) -> PasswordResetToken | None:
    """Return the matching token row when it's valid (unused + not
    expired + not pointing at a superadmin). Returns None otherwise.

    The "not a superadmin" check is belt-and-suspenders — token
    issuance excludes superadmins already, but this prevents a
    handcrafted token from honoring a row that somehow belongs to
    one.
    """
    if not raw_token:
        return None
    row = (
        db.query(PasswordResetToken)
          .filter_by(token_hash=hash_token(raw_token))
          .first()
    )
    if row is None or row.used_at is not None:
        return None
    if row.expires_at <= datetime.utcnow():
        return None
    target = db.get(User, row.user_id)
    if target is None or target.role == "superadmin":
        return None
    return row


def consume_password_reset_token(
    db: Session, token: PasswordResetToken, new_password: str,
) -> User:
    """Apply `new_password` to the token's user + mark the token
    used. Assumes `verify_password_reset_token` has already vouched
    for the token. Raises LookupError if the user is gone (race —
    deletion between verify and consume). Caller commits."""
    user = db.get(User, token.user_id)
    if user is None:
        raise LookupError(f"User id={token.user_id} no longer exists")
    user.set_password(new_password)
    token.used_at = datetime.utcnow()
    db.flush()
    return user
