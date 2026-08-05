"""TOTP + recovery-code Service.

Pure verification + minting helpers used by the login Controller's
TOTP-enroll + TOTP-verify routes.

Why these live in the Auth module:
- The 2FA flow gates login promotion (see CLAUDE.md invariant #13).
- The TOTP secret + enrollment timestamp + recovery codes all
  hang off the User row; no other module touches them.
- The Service stays HTTP-agnostic so the future FastAPI auth
  controllers can call the same code as Flask.
"""
import hashlib
import secrets

import pyotp
from sqlalchemy.orm import Session

from api.Modules.Auth.Models import RecoveryCode, User
from api.Core.Clock import utc_now


# Number of single-use recovery codes minted per (re-)enrollment.
RECOVERY_CODES_PER_USER = 10

# Roles that MUST use 2FA. Keep this the single gatekeeper —
# changing it cascades through the login route's TOTP-redirect
# check (see CLAUDE.md invariant #13).
_TOTP_REQUIRED_ROLES = ("superadmin",)

# `valid_window=1` on TOTP.verify forgives ±30s of clock drift,
# which is enough to absorb a slow phone clock or a network
# round-trip without enabling brute-force.
TOTP_VALID_WINDOW = 1


def needs_totp(user: User | None) -> bool:
    """Which users must show a TOTP/passkey factor at login. Mirrors
    the legacy `_needs_totp(user)`."""
    return bool(user and user.role in _TOTP_REQUIRED_ROLES)


def is_enrolled(user: User | None) -> bool:
    """Has this user completed TOTP enrollment? (totp_secret set AND
    totp_enrolled_at populated). Used to decide enrollment vs verify
    routes at login time."""
    return bool(user and user.totp_secret and user.totp_enrolled_at)


def verify_totp_token(user: User | None, token: str) -> bool:
    """True iff `token` is a valid current (or ±1 step) 6-digit
    code for `user`. Tolerates whitespace + non-string input.
    Caller-side errors (no secret yet, no token) just return False
    rather than raising."""
    if not (user and user.totp_secret and token):
        return False
    try:
        return pyotp.TOTP(str(user.totp_secret)).verify(
            str(token).strip(),
            valid_window=TOTP_VALID_WINDOW,
        )
    except Exception:
        return False


def hash_recovery_code(raw: str) -> str:
    """sha256-hex of the normalised (uppercase, no hyphens, no
    whitespace) recovery code. Used to compare what the user types
    against what we have in the DB."""
    normalised = raw.strip().upper().replace("-", "").replace(" ", "")
    return hashlib.sha256(normalised.encode("utf-8")).hexdigest()


def format_recovery_code(raw: str) -> str:
    """Pretty-print an 8-char code as `ABCD-EFGH` for the
    enrollment page. Pass-through for already-formatted strings."""
    s = raw.strip().upper()
    return f"{s[:4]}-{s[4:]}" if len(s) == 8 else s


def generate_recovery_codes(
    db: Session, user: User,
    *, count: int = RECOVERY_CODES_PER_USER,
) -> list[str]:
    """Wipe any existing codes for `user` and mint `count` fresh
    ones. Returns the plaintext (formatted) codes in the order they
    were inserted — the caller shows them to the user exactly once.

    Caller commits.
    """
    db.query(RecoveryCode).filter_by(user_id=user.id).delete()
    plaintext: list[str] = []
    for _ in range(count):
        raw = secrets.token_hex(4).upper()  # 8 hex chars
        plaintext.append(raw)
        db.add(RecoveryCode(
            user_id=user.id,
            code_hash=hash_recovery_code(raw),
        ))
    db.flush()
    return [format_recovery_code(c) for c in plaintext]


def consume_recovery_code(
    db: Session, user: User, raw: str,
) -> bool:
    """Return True iff `raw` matches an unused code for `user` and
    mark it used. `raw` may be pasted with or without the hyphen.
    Caller commits."""
    if not raw:
        return False
    row = (
        db.query(RecoveryCode)
          .filter_by(
              user_id=user.id,
              code_hash=hash_recovery_code(raw),
              used_at=None,
          )
          .first()
    )
    if row is None:
        return False
    setattr(row, "used_at", utc_now())
    db.flush()
    return True
