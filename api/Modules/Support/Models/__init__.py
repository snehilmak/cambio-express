"""Support — Models.

``SupportTicket`` — one row per user-submitted ticket (bug report,
feature request, question, or general feedback). Scoped to
``(store_id, user_id)`` so store admins see their store's tickets
and superadmin sees everything.
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
    store_id    = Column(Integer, ForeignKey("store.id"), nullable=False, index=True)
    user_id     = Column(Integer, ForeignKey("user.id"), nullable=False, index=True)
    submitted_by = Column(String(120), nullable=False)
    category    = Column(String(30), nullable=False, default="question")
    priority    = Column(String(10), nullable=True)
    subject     = Column(String(200), nullable=False)
    body        = Column(Text, nullable=False)
    status      = Column(String(20), nullable=False, default="open")
    admin_reply = Column(Text, nullable=True)
    replied_at  = Column(DateTime, nullable=True)
    replied_by  = Column(String(120), nullable=True)
    created_at  = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at  = Column(DateTime, default=datetime.utcnow,
                          onupdate=datetime.utcnow, nullable=False)
    closed_at   = Column(DateTime, nullable=True)


__all__ = ["SupportTicket"]
