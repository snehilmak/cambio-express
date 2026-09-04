"""Batches — Models.

* ``ACHBatch`` — one ACH withdrawal that settles a day's transfers
                 with a money-transfer company.

``Transfer`` is re-exported from ``api/Modules/Transfers/Models`` so
existing ``from api.Modules.Batches.Models import Transfer`` call
sites keep working.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger, Boolean, Column, Date, DateTime, ForeignKey, Integer,
    String, UniqueConstraint, func,
)
from sqlalchemy.orm import Session

from api.Core.Database import Base
from api.Core.Money import to_cents, to_dollars


class ACHBatch(Base):
    __tablename__ = "msb_ach_batch"
    id             = Column(Integer, primary_key=True)
    store_id       = Column(Integer, ForeignKey("tenancy_store.id"), nullable=False)
    ach_date       = Column(Date, nullable=False)
    company        = Column(String(30), nullable=False)
    batch_ref      = Column(String(60), nullable=False)
    # Integer cents (P0-3) — dollar view via the @property below.
    ach_amount_cents = Column(BigInteger, nullable=False, default=0)
    transfer_dates = Column(String(60), default="")
    status         = Column(String(30), default="Pending")
    reconciled     = Column(Boolean, default=False)
    notes          = Column(String(255), default="")
    created_at     = Column(DateTime, default=datetime.utcnow)
    __table_args__ = (UniqueConstraint("store_id", "batch_ref"),)

    @property
    def ach_amount(self) -> float:
        return to_dollars(self.ach_amount_cents)  # type: ignore[arg-type]

    @ach_amount.setter
    def ach_amount(self, dollars: object) -> None:
        self.ach_amount_cents = to_cents(dollars)  # type: ignore[assignment]

    @property
    def transfers_total_cents(self) -> int:
        """Sum of what the ACH actually debits, in exact cents:
        send amount + federal tax. The store fee stays with the
        store, so it's excluded from this total."""
        # Lazy import to avoid Transfer ↔ ACHBatch module-import cycle.
        from api.Modules.Transfers.Models import Transfer
        s = Session.object_session(self)
        if s is None:
            return 0
        v = (s.query(
                func.coalesce(func.sum(Transfer.send_amount_cents), 0)
              + func.coalesce(func.sum(Transfer.federal_tax_cents), 0))
             .filter_by(store_id=self.store_id, batch_id=self.batch_ref)
             .filter(Transfer.status != "Cancelled")
             .scalar())
        return int(v or 0)

    @property
    def transfers_total(self) -> float:
        return to_dollars(self.transfers_total_cents)

    @property
    def variance_cents(self) -> int:
        return int(self.ach_amount_cents or 0) - self.transfers_total_cents

    @property
    def variance(self) -> float:
        return to_dollars(self.variance_cents)

    @property
    def transfer_count(self) -> int:
        from api.Modules.Transfers.Models import Transfer
        s = Session.object_session(self)
        if s is None:
            return 0
        return int(s.query(Transfer).filter_by(
            store_id=self.store_id, batch_id=self.batch_ref,
        ).filter(Transfer.status != "Cancelled").count())


# Re-export Transfer so existing
# ``from api.Modules.Batches.Models import Transfer`` keeps working.
def __getattr__(name: str) -> Any:
    # Lazy fallthrough avoids the Batches ↔ Transfers module cycle
    # at import time. Only fires the first time ``Transfer`` is
    # looked up on this module.
    if name == "Transfer":
        from api.Modules.Transfers.Models import Transfer as _T
        globals()["Transfer"] = _T
        return _T
    raise AttributeError(name)


__all__ = ["ACHBatch", "Transfer"]
