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

    __tablename__ = "audit_operator_log"
    id           = Column(Integer, primary_key=True)
    store_id     = Column(Integer, ForeignKey("tenancy_store.id"), nullable=False, index=True)
    user_id      = Column(Integer, ForeignKey("tenancy_user.id"), nullable=True)
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

    __tablename__ = "audit_transfer"
    id             = Column(Integer, primary_key=True)
    store_id       = Column(Integer, ForeignKey("tenancy_store.id"), nullable=False, index=True)
    transfer_id    = Column(Integer, ForeignKey("msb_transfer.id"), nullable=False)
    user_id        = Column(Integer, ForeignKey("tenancy_user.id"), nullable=True)
    employee_id    = Column(Integer, ForeignKey("tenancy_store_employee.id"), nullable=True)
    employee_name  = Column(String(120), default="")
    action         = Column(String(30), nullable=False)   # created | updated | status_changed
    summary        = Column(String(500), default="")
    created_at     = Column(DateTime, default=datetime.utcnow)
    user           = relationship("User", foreign_keys=[user_id])


class SuperadminAuditLog(Base):
    """Append-only record of platform-admin actions for traceability."""

    __tablename__ = "audit_superadmin_log"
    id          = Column(Integer, primary_key=True)
    admin_id    = Column(Integer, ForeignKey("tenancy_user.id"), nullable=True)
    admin_name  = Column(String(120), default="")  # snapshot in case the user row is deleted
    action      = Column(String(60), nullable=False)   # e.g. "extend_trial", "comp_plan"
    target_type = Column(String(30), default="")       # "store" | "discount" | "feature"
    target_id   = Column(String(60), default="")
    details     = Column(Text, default="")             # free-form, usually short JSON/text
    created_at  = Column(DateTime, default=datetime.utcnow)


class OwnerAuditLog(Base):
    """Append-only audit log for multi-store OWNER actions that
    aren't scoped to a single store — connect-code mint / revoke,
    and other owner-umbrella mutations added later.

    Why its own table: owners span many stores, so these don't fit
    the store-scoped ``OperatorAuditLog`` (there's no single
    ``store_id`` to hang them on); and the actor is an owner, not a
    platform superadmin, so ``SuperadminAuditLog`` would misattribute
    them. ``owner_name`` is a snapshot so the row still identifies the
    actor after the User row is deleted.

    Append-only; read by the owner activity surface (future). Not a
    per-store model, so it's intentionally NOT in the retention
    purge's ``_STORE_OWNED_MODELS`` list.
    """

    __tablename__ = "audit_owner_log"
    id           = Column(Integer, primary_key=True)
    owner_id     = Column(Integer, ForeignKey("tenancy_user.id"), nullable=False, index=True)
    owner_name   = Column(String(120), default="")
    action       = Column(String(40), nullable=False)
    target_type  = Column(String(30), default="")
    target_id    = Column(String(60), default="")
    details      = Column(Text, default="")
    created_at   = Column(DateTime, default=datetime.utcnow)
    owner        = relationship("User", foreign_keys=[owner_id])


__all__ = [
    "OperatorAuditLog",
    "OwnerAuditLog",
    "SuperadminAuditLog",
    "TransferAudit",
]
