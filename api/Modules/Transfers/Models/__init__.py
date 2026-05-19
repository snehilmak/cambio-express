"""Transfers — Models.

* ``Transfer`` — one row per remittance / bill payment / top-up
                 logged by a cashier. The core revenue-bearing
                 entity.

Re-exports of ``ACHBatch``, ``Customer``, ``Store``, ``User`` cover
the Transfers services' existing import surface.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Column, Date, DateTime, Float, ForeignKey, Index, Integer, String,
)
from sqlalchemy.orm import relationship

from api.Core.Database import Base


class Transfer(Base):
    __tablename__ = "transfer"
    id             = Column(Integer, primary_key=True)
    store_id       = Column(Integer, ForeignKey("store.id"), nullable=False)
    created_by     = Column(Integer, ForeignKey("user.id"))
    # Linked to Customer for returning-customer autofill. Nullable so
    # legacy transfers stay valid.
    customer_id    = Column(Integer, ForeignKey("customer.id"), nullable=True)
    send_date      = Column(Date, nullable=False)
    company        = Column(String(30), nullable=False)
    # Service performed for the customer. Money Transfer is the
    # historical default — we still apply ``Store.federal_tax_rate``
    # to it. Bill Payment, Top Up, and Recharge are non-remittance
    # services that the cashier also runs through the same companies,
    # but the federal tax doesn't apply (no ACH withdrawal that would
    # carry it). Server-side tax math in new_transfer / edit_transfer
    # is the gate, not this column.
    service_type   = Column(String(30), default="Money Transfer", nullable=False)
    sender_name    = Column(String(120), nullable=False)
    send_amount    = Column(Float, nullable=False)
    fee            = Column(Float, default=0.0)
    # Federal tax (e.g. 1%) the customer pays on the send amount.
    # Tracked separately from ``fee`` because it leaves the store
    # with the ACH withdrawal — it's not store revenue.
    federal_tax    = Column(Float, default=0.0)
    commission     = Column(Float, default=0.0)
    recipient_name = Column(String(120), default="")
    country        = Column(String(60), default="")
    recipient_phone= Column(String(40), default="")
    # Sender snapshot: a copy of Customer fields at transfer time.
    # The canonical source of truth is the linked Customer row so
    # updates flow both ways — we mirror here so old transfers still
    # display even after a customer edits their info or the Customer
    # row is deleted.
    sender_phone        = Column(String(40), default="")
    sender_phone_country= Column(String(8),  default="")
    sender_address      = Column(String(255), default="")
    sender_dob          = Column(Date, nullable=True)
    confirm_number = Column(String(60), default="")
    status         = Column(String(30), default="Sent")
    status_notes   = Column(String(255), default="")
    batch_id       = Column(String(60), default="")
    internal_notes = Column(String(255), default="")
    # Processed-by attribution (separate from the login user under
    # ``created_by``): ``employee_id`` links to the store's
    # named-employee roster for analytics; ``employee_name`` is the
    # string snapshot captured at save-time so historical transfers
    # display the correct name forever — even if the roster row is
    # later deactivated, renamed, or deleted.
    employee_id    = Column(Integer, ForeignKey("store_employee.id"), nullable=True)
    employee_name  = Column(String(120), default="")
    created_at     = Column(DateTime, default=datetime.utcnow)
    updated_at     = Column(DateTime, default=datetime.utcnow)
    creator        = relationship("User", foreign_keys=[created_by])
    employee       = relationship("StoreEmployee", foreign_keys=[employee_id])
    # Indexes for the hot-path queries:
    # • (store_id, send_date)   the period filter every Reports aggregator uses
    # • customer_id             the umbrella-customer + new-vs-returning lookup
    # • created_by              the sales-by-employee + employee-activity reports
    # • status                  the active-vs-cancelled filter on every list view
    # • confirm_number          the transfers-list "look up by confirmation #" search
    __table_args__ = (
        Index("ix_transfer_store_send_date", "store_id", "send_date"),
        Index("ix_transfer_customer_id",    "customer_id"),
        Index("ix_transfer_created_by",     "created_by"),
        Index("ix_transfer_status",         "status"),
        Index("ix_transfer_confirm_number", "confirm_number"),
    )

    @property
    def total_collected(self) -> float:
        """What the customer actually handed over: send amount +
        store fee + federal tax."""
        return float(
            (self.send_amount or 0)
            + (self.fee or 0)
            + (self.federal_tax or 0)
        )


# Re-export the surrounding entities the Transfers services touch.
from api.Modules.Batches.Models import ACHBatch  # noqa: E402
from api.Modules.Customers.Models import Customer  # noqa: E402
from api.Modules.Tenancy.Models import Store, User  # noqa: E402


__all__ = ["ACHBatch", "Customer", "Store", "Transfer", "User"]
