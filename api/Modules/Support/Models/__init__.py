"""Support — Models.

``SupportTicket`` — one row per user-submitted ticket (bug report,
feature request, question, or general feedback). Scoped to
``(store_id, user_id)`` so store admins see their store's tickets
and superadmin sees everything.

``SupportMessage`` — one row per reply in a ticket's conversation
thread (chat-style, both directions). The legacy
``SupportTicket.admin_reply`` column predates the thread: it held a
single overwritable staff reply. It's kept (and dual-written with
the latest staff message) for back-compat, but the thread is the
source of truth — existing replies were backfilled into messages by
the ``d2e8b4f6a1c3`` migration.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Column, DateTime, ForeignKey, Integer, String, Text,
)

from api.Core.Database import Base


class SupportTicket(Base):
    __tablename__ = "support_ticket"
    id          = Column(Integer, primary_key=True)
    store_id    = Column(Integer, ForeignKey("tenancy_store.id"), nullable=False, index=True)
    user_id     = Column(Integer, ForeignKey("tenancy_user.id"), nullable=False, index=True)
    submitted_by = Column(String(120), nullable=False)
    category    = Column(String(30), nullable=False, default="question")
    priority    = Column(String(10), nullable=True)
    subject     = Column(String(200), nullable=False)
    body        = Column(Text, nullable=False)
    status      = Column(String(20), nullable=False, default="open")
    admin_reply = Column(Text, nullable=True)
    replied_at  = Column(DateTime, nullable=True)
    replied_by  = Column(String(120), nullable=True)
    # Claim/assignment — which platform-staff person is working the
    # ticket. ``assigned_to_name`` is a display snapshot (same
    # pattern as ``submitted_by``); the FK is the authority.
    assigned_to_user_id = Column(Integer, ForeignKey("tenancy_user.id"), nullable=True)
    assigned_to_name    = Column(String(120), nullable=True)
    # Per-SIDE read receipts for the in-app unread badge. Each side
    # (store users vs platform staff) shares one marker — the read
    # state is per conversation side, not per person, matching the
    # shared-inbox scoping of the list endpoints. NULL = that side
    # has never opened the thread since the feature shipped, so every
    # opposite-side message counts as unread.
    user_last_seen_at  = Column(DateTime, nullable=True)
    staff_last_seen_at = Column(DateTime, nullable=True)
    created_at  = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at  = Column(DateTime, default=datetime.utcnow,
                          onupdate=datetime.utcnow, nullable=False)
    closed_at   = Column(DateTime, nullable=True)


class SupportMessage(Base):
    """One reply in a ticket's conversation thread.

    ``store_id`` is denormalized from the ticket so the retention
    purge (`_STORE_OWNED_MODELS`, invariant #4) can cascade by
    store without joining through the ticket. ``author_name`` is a
    display snapshot (like ``SupportTicket.submitted_by``) so the
    thread stays readable if the user row is later deleted.
    ``author_kind`` is ``"user"`` (someone at the store) or
    ``"staff"`` (platform side) — it drives the chat-bubble side
    in the UI.
    """
    __tablename__ = "support_message"
    id             = Column(Integer, primary_key=True)
    ticket_id      = Column(Integer, ForeignKey("support_ticket.id"),
                            nullable=False, index=True)
    store_id       = Column(Integer, ForeignKey("tenancy_store.id"),
                            nullable=False, index=True)
    author_user_id = Column(Integer, ForeignKey("tenancy_user.id"), nullable=True)
    author_name    = Column(String(120), nullable=False, default="")
    author_kind    = Column(String(10), nullable=False, default="user")
    body           = Column(Text, nullable=False)
    created_at     = Column(DateTime, default=datetime.utcnow, nullable=False)


__all__ = ["SupportMessage", "SupportTicket"]
