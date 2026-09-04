"""Announcements — Models.

Two classes:

* ``Announcement``     — global banner the superadmin can post.
* ``PushSubscription`` — Web Push endpoint for a user (one row per
                         browser/device they opted in on).
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean, Column, DateTime, ForeignKey, Integer, String, Text,
    UniqueConstraint,
)

from api.Core.Database import Base


class Announcement(Base):
    """Global banner the superadmin can post across the app.

    Shown on every admin/employee page between ``starts_at`` and
    ``expires_at`` while ``is_active``. ``level`` maps onto the
    banner-* utility classes in ``app.css``.
    """

    __tablename__ = "platform_announcement"
    id         = Column(Integer, primary_key=True)
    message    = Column(Text, nullable=False)
    level      = Column(String(16), default="info")  # info | warning | error | success
    is_active  = Column(Boolean, default=True)
    starts_at  = Column(DateTime, nullable=True)
    expires_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    created_by = Column(Integer, ForeignKey("tenancy_user.id"), nullable=True)
    # Broadcast-email flags. ``broadcast_requested`` is set when the
    # superadmin ticks the "Also email all users" checkbox at create
    # time. ``broadcast_sent_at`` is stamped the first time
    # ``broadcast_announcement()`` actually sends; used to dedup if
    # the announcement is edited later or the sender is run manually.
    broadcast_requested  = Column(Boolean, default=False)
    broadcast_sent_at    = Column(DateTime, nullable=True)


class AnnouncementStore(Base):
    """Targets an ``Announcement`` at one specific ``Store``.

    The presence of ANY row for an announcement makes it *targeted*:
    only stores with a matching row see the banner (and only their
    users receive the broadcast email). The ABSENCE of any row means
    the announcement is *global* — visible to every store, which is
    the back-compat default for every announcement created before
    targeting shipped.

    One row per (announcement, store) pair. Deleting an announcement
    must delete its rows here first (FK ``announcement_id`` →
    ``announcement.id``); purging a store deletes its rows here via
    the retention registry (FK ``store_id`` → ``store.id``,
    invariant #4).
    """

    __tablename__ = "platform_announcement_store"
    id              = Column(Integer, primary_key=True)
    announcement_id = Column(
        Integer, ForeignKey("platform_announcement.id"), nullable=False,
    )
    store_id        = Column(Integer, ForeignKey("tenancy_store.id"), nullable=False)
    __table_args__ = (
        UniqueConstraint("announcement_id", "store_id"),
    )


class PushSubscription(Base):
    """Web Push endpoint for a user — one row per browser/device they
    opted in on. Deleted on unsubscribe or when the endpoint starts
    returning 404/410 from the push provider."""

    __tablename__ = "platform_push_subscription"
    id         = Column(Integer, primary_key=True)
    user_id    = Column(Integer, ForeignKey("tenancy_user.id"), nullable=False)
    endpoint   = Column(Text, nullable=False)
    p256dh     = Column(String(200), nullable=False)
    auth       = Column(String(80), nullable=False)
    user_agent = Column(String(255), default="")
    created_at = Column(DateTime, default=datetime.utcnow)
    __table_args__ = (UniqueConstraint("user_id", "endpoint"),)


__all__ = ["Announcement", "AnnouncementStore", "PushSubscription"]
