"""Active-session listing + revocation.

A "session" is the chain of refresh tokens that share one
``session_id`` — one browser, one login, one cookie jar. The
chain spans every rotation (every ``/auth/refresh`` call), so a
user who's been signed in for two weeks has ONE session even
though the underlying refresh row has been rotated dozens of
times.

Two surfaces:

  * ``list_active_sessions(db, user_id, current_session_id)``
    returns one row per (user_id, session_id) for the user.
    Picks the head of the chain (the most-recent, non-revoked,
    non-expired token) so the returned ``user_agent`` /
    ``ip_address`` / ``last_used_at`` reflect the latest
    refresh. The current session (matched by JWT claim) is
    flagged with ``is_current=True``.

  * ``revoke_session(db, user_id, session_id)`` flips
    ``revoked_at`` on every row in the chain for that user.
    Refresh attempts on any of those jtis 401. Restricting by
    user_id stops one user from killing another's session.

Legacy rows with ``session_id=NULL`` (rows that pre-date the
session_id column) are bucketed as a SINGLE legacy session per
user — the user can still sign them out via "Sign out other
devices" without needing data backfill.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from api.Modules.Auth.Models import RefreshToken
from api.Core.Clock import utc_now


# Sentinel used for legacy rows with ``session_id=NULL`` in the
# list-endpoint response — gives the SPA a stable string key while
# keeping the database column nullable for backwards compat.
LEGACY_SESSION_ID = "legacy"


@dataclass(frozen=True)
class ActiveSession:
    """One row in the sessions panel."""
    session_id:   str
    user_agent:   str
    ip_address:   str
    started_at:   datetime  # head row's created_at
    last_used_at: datetime  # same as started_at — head row IS the latest
    expires_at:   datetime
    is_current:   bool


def _is_alive(row: RefreshToken, now: datetime) -> bool:
    """A refresh row is alive when it hasn't been revoked AND
    hasn't expired. The list endpoint only counts live rows so a
    chain whose head is dead doesn't appear as an active session."""
    if row.revoked_at is not None:
        return False
    if row.expires_at <= now:
        return False
    return True


def list_active_sessions(
    db: Session,
    *,
    user_id: int,
    current_session_id: Optional[str] = None,
) -> list[ActiveSession]:
    """Return one ``ActiveSession`` per distinct ``session_id``
    chain owned by ``user_id`` whose HEAD token is still alive.

    "Head" = the most recently created live row for that chain.
    Its ``user_agent`` / ``ip_address`` / ``created_at`` are what
    we surface — the chain's earlier rows are revoked-by-rotation
    by construction.

    ``current_session_id`` (typically pulled from the access
    token's ``sid`` claim) is used to flag the caller's own
    session in the response so the SPA can render it differently
    ("This device — signed in just now"). Pass ``None`` if the
    JWT doesn't carry the claim (older login paths) — every row
    falls back to ``is_current=False``.
    """
    now = utc_now()
    rows = (
        db.query(RefreshToken)
          .filter(RefreshToken.user_id == user_id)
          .order_by(RefreshToken.created_at.desc())
          .all()
    )
    # Walk newest → oldest, keeping the first live row per chain.
    by_chain: dict[str, RefreshToken] = {}
    for r in rows:
        if not _is_alive(r, now):
            continue
        key = r.session_id or LEGACY_SESSION_ID
        if key in by_chain:
            continue
        by_chain[key] = r

    sessions: list[ActiveSession] = []
    for key, head in by_chain.items():
        sessions.append(ActiveSession(
            session_id=key,
            user_agent=head.user_agent or "",
            ip_address=head.ip_address or "",
            started_at=head.created_at,
            last_used_at=head.created_at,
            expires_at=head.expires_at,
            is_current=bool(
                current_session_id is not None
                and key == current_session_id
            ),
        ))
    # Most-recently-used first.
    sessions.sort(key=lambda s: s.last_used_at, reverse=True)
    return sessions


def revoke_session(
    db: Session,
    *,
    user_id: int,
    session_id: str,
) -> int:
    """Flip ``revoked_at`` on every refresh row for the (user,
    session) pair. Returns the number of rows actually revoked
    (already-revoked + expired rows aren't touched). Returns 0
    if no rows matched — that's the same outcome as "already
    revoked" so the caller's response shape stays constant.

    The ``user_id`` filter is the security boundary: a caller can
    only revoke their OWN sessions. Cross-user revoke attempts
    return 0 (404-shaped at the controller).

    Handles the legacy bucket: passing ``session_id=LEGACY_SESSION_ID``
    revokes every live refresh row with NULL ``session_id`` for
    the user (the singleton legacy chain)."""
    now = utc_now()
    q = (
        db.query(RefreshToken)
          .filter(
              RefreshToken.user_id == user_id,
              RefreshToken.revoked_at.is_(None),
          )
    )
    if session_id == LEGACY_SESSION_ID:
        q = q.filter(RefreshToken.session_id.is_(None))
    else:
        q = q.filter(RefreshToken.session_id == session_id)

    affected = 0
    for row in q.all():
        row.revoked_at = now
        affected += 1
    db.flush()
    return affected


def revoke_other_sessions(
    db: Session,
    *,
    user_id: int,
    keep_session_id: str,
) -> int:
    """Revoke every live session for the user EXCEPT the one
    matching ``keep_session_id``. Used by the "Sign out other
    devices" button so a user can drop suspicious sessions
    without losing their current login.

    Returns the count of refresh rows revoked (sum across every
    revoked chain).
    """
    now = utc_now()
    q = (
        db.query(RefreshToken)
          .filter(
              RefreshToken.user_id == user_id,
              RefreshToken.revoked_at.is_(None),
          )
    )
    if keep_session_id == LEGACY_SESSION_ID:
        q = q.filter(RefreshToken.session_id.isnot(None))
    else:
        # Anything not in the keep chain.
        from sqlalchemy import or_
        q = q.filter(or_(
            RefreshToken.session_id.is_(None),
            RefreshToken.session_id != keep_session_id,
        ))

    affected = 0
    for row in q.all():
        row.revoked_at = now
        affected += 1
    db.flush()
    return affected


__all__ = [
    "ActiveSession",
    "LEGACY_SESSION_ID",
    "list_active_sessions",
    "revoke_other_sessions",
    "revoke_session",
]
