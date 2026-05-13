"""Audit — Models.

Three append-only audit-log tables:

* ``OperatorAuditLog``   — store-side actions on objects without
                           their own dedicated audit table (daily
                           reports, ACH batches, transfer deletes).
* ``TransferAudit``      — every change to a Transfer row
                           (create / edit / status change). Shown
                           on the transfer edit page.
* ``SuperadminAuditLog`` — platform-admin actions (extend trial,
                           comp plan, etc.) for traceability.

Moved out of ``app.py`` as the second slice of the Final-phase
model-extraction work. ``app.py`` re-exports the names so every
``from app import OperatorAuditLog`` keeps working.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from api.Core.Database import Base


class OperatorAuditLog(Base):
    """Generic store-side audit log for operator actions on objects
    that don't have their own dedicated audit table (daily reports,
    ACH batches, transfer deletes). Transfers themselves use the
    older ``TransferAudit`` table, which is FK-tied to Transfer rows
    and gets cascade-cleared on transfer delete — so we log the
    delete here too, where it survives the row it describes.

    Append-only. Read by the admin /admin/audit-log page. Never
    edited or deleted by the app code (purge-expired-stores is the
    only reaper, via ``_STORE_OWNED_MODELS``).
    """

    __tablename__ = "operator_audit_log"
    id           = Column(Integer, primary_key=True)
    store_id     = Column(Integer, ForeignKey("store.id"), nullable=False, index=True)
    user_id      = Column(Integer, ForeignKey("user.id"), nullable=True)
    user_name    = Column(String(120), default="")
    user_role    = Column(String(20),  default="")
    target_type  = Column(String(30),  nullable=False)
    target_id    = Column(String(60),  default="")
    target_label = Column(String(160), default="")
    action       = Column(String(30),  nullable=False)
    summary      = Column(Text, default="")
    created_at   = Column(DateTime, default=datetime.utcnow)
    user         = relationship("User", foreign_keys=[user_id])


class TransferAudit(Base):
    """Append-only log of everything that happens to a Transfer.

    Written on create, on edit (with a human-readable summary of which
    fields changed and their before→after values), and on status
    changes. Shown to admins on the transfer edit page so they can
    see exactly who touched a record and when. ``user_id`` is the
    logged-in User; ``employee_name`` is the roster name they
    credited the action to (snapshot string, not FK, so it stays
    valid after the roster row is deactivated).
    """

    __tablename__ = "transfer_audit"
    id             = Column(Integer, primary_key=True)
    store_id       = Column(Integer, ForeignKey("store.id"), nullable=False, index=True)
    transfer_id    = Column(Integer, ForeignKey("transfer.id"), nullable=False)
    user_id        = Column(Integer, ForeignKey("user.id"), nullable=True)
    employee_id    = Column(Integer, ForeignKey("store_employee.id"), nullable=True)
    employee_name  = Column(String(120), default="")
    action         = Column(String(30), nullable=False)   # created | updated | status_changed
    summary        = Column(String(500), default="")
    created_at     = Column(DateTime, default=datetime.utcnow)
    user           = relationship("User", foreign_keys=[user_id])


class SuperadminAuditLog(Base):
    """Append-only record of platform-admin actions for traceability."""

    __tablename__ = "superadmin_audit_log"
    id          = Column(Integer, primary_key=True)
    admin_id    = Column(Integer, ForeignKey("user.id"), nullable=True)
    admin_name  = Column(String(120), default="")  # snapshot in case the user row is deleted
    action      = Column(String(60), nullable=False)   # e.g. "extend_trial", "comp_plan"
    target_type = Column(String(30), default="")       # "store" | "discount" | "feature"
    target_id   = Column(String(60), default="")
    details     = Column(Text, default="")             # free-form, usually short JSON/text
    created_at  = Column(DateTime, default=datetime.utcnow)


__all__ = ["OperatorAuditLog", "SuperadminAuditLog", "TransferAudit"]
