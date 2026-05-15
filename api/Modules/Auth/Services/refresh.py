"""Refresh-token issuance + rotation + revocation.

Pairs with the httpOnly access-token cookie added in PR #559 to
implement silent refresh: when the SPA's 30-minute access JWT
expires mid-workflow, the SPA hits ``/auth/refresh`` and the
server mints a fresh access + refresh pair via ``rotate()`` —
the old refresh row is marked ``revoked_at`` and ``rotated_to_id``
points at its successor.

Rotation + revocation give us two things a stateless JWT can't:

  1. **Server-side logout**. ``revoke(jti)`` (called from
     ``/auth/logout``) ends the session immediately — the old
     access JWT is still cryptographically valid until its 30-
     minute exp, but the refresh row is dead, so the next 401
     can't recover.

  2. **Replay detection**. If the same refresh token is presented
     twice (legitimate user already rotated past it), one of
     those calls is an attacker replaying a stolen cookie. The
     repeat is rejected and the whole chain is burned —
     ``rotated_to_id`` lets ops trace the chain backward + forward
     for forensics.

The refresh secret never leaves the server-side cookie. It's a
URL-safe 32-byte (256-bit) random string; we store the bare value
in ``RefreshToken.jti`` so a single index lookup at refresh time
runs in O(1).
"""
from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from api.Modules.Auth.Models import RefreshToken


# 14 days — long enough that returning users don't see a login
# screen on their next visit, short enough that a stolen cookie
# stops working before the original user is likely to notice.
DEFAULT_REFRESH_TOKEN_TTL_SECONDS = 14 * 24 * 60 * 60


@dataclass(frozen=True)
class IssuedRefreshToken:
    """Result of ``issue`` / ``rotate``: the opaque token string
    (returned to the client in the cookie) + the database row's
    expiry (used by the caller to set the cookie's Max-Age)."""

    jti: str
    expires_at: datetime
    user_id: int


def _now() -> datetime:
    """Wall-clock — one place to mock in tests if we ever need to."""
    return datetime.utcnow()


def _mint_jti() -> str:
    """256-bit URL-safe random secret. ``secrets.token_urlsafe(32)``
    yields ~43 chars; well under the ``VARCHAR(64)`` cap."""
    return secrets.token_urlsafe(32)


def issue(
    session: Session, *, user_id: int,
    ttl_seconds: int = DEFAULT_REFRESH_TOKEN_TTL_SECONDS,
) -> IssuedRefreshToken:
    """Mint a fresh refresh token for ``user_id`` and persist it.
    Called from every login path (password / 2FA / signup) right
    after the access JWT is issued."""
    now = _now()
    expires_at = now + timedelta(seconds=ttl_seconds)
    jti = _mint_jti()
    session.add(RefreshToken(
        jti=jti,
        user_id=user_id,
        created_at=now,
        expires_at=expires_at,
    ))
    session.flush()
    return IssuedRefreshToken(jti=jti, expires_at=expires_at, user_id=user_id)


def _lookup_active(
    session: Session, jti: str,
) -> Optional[RefreshToken]:
    """Find a refresh row by jti. Returns the row even if it's
    revoked or expired — caller checks; we want the revoked / expired
    state visible for the replay-detection branch."""
    return (
        session.query(RefreshToken)
        .filter(RefreshToken.jti == jti)
        .first()
    )


class RefreshTokenInvalid(Exception):
    """Generic refresh failure. Caller (controller) translates to a
    401 + cookie-clear. Specific subclasses surface so the audit log
    can distinguish 'expired' from 'replay'."""


class RefreshTokenExpired(RefreshTokenInvalid):
    """The token's ``expires_at`` is in the past."""


class RefreshTokenRevoked(RefreshTokenInvalid):
    """The token was revoked (logout, rotation, or replay)."""


class RefreshTokenUnknown(RefreshTokenInvalid):
    """No row matches the presented jti. Either a forged cookie or
    the row was deleted (rare — we keep revoked rows for audit)."""


def rotate(
    session: Session, *, jti: str,
    ttl_seconds: int = DEFAULT_REFRESH_TOKEN_TTL_SECONDS,
) -> tuple[RefreshToken, IssuedRefreshToken]:
    """Validate the presented refresh token, mint a successor, mark
    the old row revoked + linked to the new one. Returns the OLD
    row (so the caller can read ``user_id``) + the new
    ``IssuedRefreshToken`` (jti + expiry for the cookie).

    Replay detection: if the presented token is already revoked,
    raise ``RefreshTokenRevoked``. The legitimate user rotated past
    it; this call is an attacker replaying a captured cookie. The
    caller's response is to clear cookies and 401 — and ideally
    audit the event.
    """
    now = _now()
    row = _lookup_active(session, jti)
    if row is None:
        raise RefreshTokenUnknown()
    if row.revoked_at is not None:
        # Replay. Don't extend any state — the chain is already
        # dead. Audit + 401.
        raise RefreshTokenRevoked()
    if row.expires_at <= now:
        # Mark expired rows revoked too so a later attempt with the
        # same jti hits the 'revoked' branch instead of 'expired'.
        row.revoked_at = now
        session.flush()
        raise RefreshTokenExpired()

    # Mint the successor, then revoke + link the old row.
    new = issue(session, user_id=row.user_id, ttl_seconds=ttl_seconds)
    successor = _lookup_active(session, new.jti)
    assert successor is not None  # we just inserted it
    row.revoked_at = now
    row.rotated_to_id = successor.id
    session.flush()
    return row, new


def revoke(session: Session, *, jti: str) -> bool:
    """Hard-revoke a refresh row. Called from ``/auth/logout``.
    Returns ``True`` if a row was revoked, ``False`` if no live
    row matched (already gone — same effect)."""
    row = _lookup_active(session, jti)
    if row is None or row.revoked_at is not None:
        return False
    row.revoked_at = _now()
    session.flush()
    return True


__all__ = [
    "DEFAULT_REFRESH_TOKEN_TTL_SECONDS",
    "IssuedRefreshToken",
    "RefreshTokenExpired",
    "RefreshTokenInvalid",
    "RefreshTokenRevoked",
    "RefreshTokenUnknown",
    "issue",
    "revoke",
    "rotate",
]
