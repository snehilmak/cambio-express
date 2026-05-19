"""Per-user push subscription CRUD.

Lives in Auth/Services because subscriptions hang off the
``User`` row + the controller surface is the personal
"Notifications" account page.  The ``PushSubscription`` model
itself lives in Announcements/Models alongside ``Announcement``
because broadcasts are the v1 producer; that's a historical
artifact + isn't worth re-homing.

The Web Push transport itself lives in
``api/Modules/Notifications/Services/push.py``.  This module
manages the subscription rows that drive that transport's
delivery loop.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from api.Modules.Announcements.Models import PushSubscription
from api.Modules.Auth.Models import User


def push_status_payload(db: Session, user: User) -> dict[str, Any]:
    """Status envelope returned to the SPA so it can decide whether
    to show the "Enable browser notifications" CTA + the toggle's
    current state."""
    from api.Modules.Notifications.Services.push import (
        is_enabled,
        vapid_public_key,
    )
    count = (
        db.query(PushSubscription)
          .filter_by(user_id=user.id)
          .count()
    )
    return {
        "enabled":      is_enabled(),
        "public_key":   vapid_public_key(),
        "subscribed":   count > 0,
        "device_count": int(count),
    }


def upsert_push_subscription(
    db: Session,
    user: User,
    *,
    endpoint: str,
    p256dh: str,
    auth: str,
    user_agent: str = "",
) -> PushSubscription:
    """Register a browser push subscription for ``user``.

    Idempotent: if the same ``(user_id, endpoint)`` pair already
    exists (operator re-enabled push on the same device, e.g.),
    we update the crypto material in place rather than insert a
    duplicate row.  The model has a UNIQUE constraint on those
    two columns, so the alternative would be a 409 on every
    re-enable.

    Caller commits.
    """
    existing = (
        db.query(PushSubscription)
          .filter_by(user_id=user.id, endpoint=endpoint)
          .first()
    )
    if existing is not None:
        setattr(existing, "p256dh",     p256dh)
        setattr(existing, "auth",       auth)
        setattr(existing, "user_agent", user_agent or "")
        db.flush()
        return existing
    row = PushSubscription(
        user_id=int(user.id),
        endpoint=endpoint,
        p256dh=p256dh,
        auth=auth,
        user_agent=user_agent or "",
    )
    db.add(row)
    db.flush()
    return row


def delete_push_subscription(
    db: Session, user: User, *, endpoint: str,
) -> int:
    """Drop the user's subscription matching ``endpoint``.  Returns
    the number of rows deleted (0 if no match, 1 otherwise).

    Idempotent: a second DELETE for the same endpoint after the
    first succeeded returns 0 with no error.  Caller commits.
    """
    rows = (
        db.query(PushSubscription)
          .filter_by(user_id=user.id, endpoint=endpoint)
          .all()
    )
    for r in rows:
        db.delete(r)
    db.flush()
    return len(rows)
