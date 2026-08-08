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
    Boolean, Column, Date, DateTime, Float, ForeignKey, Integer, String,
    UniqueConstraint, func,
)
from sqlalchemy.orm import Session

from api.Core.Database import Base


class ACHBatch(Base):
    __tablename__ = "ach_batch"
    id             = Column(Integer, primary_key=True)
    store_id       = Column(Integer, ForeignKey("store.id"), nullable=False)
    ach_date       = Column(Date, nullable=False)
    company        = Column(String(30), nullable=False)
    batch_ref      = Column(String(60), nullable=False)
    ach_amount     = Column(Float, nullable=False)
    transfer_dates = Column(String(60), default="")
    status         = Column(String(30), default="Pending")
    reconciled     = Column(Boolean, default=False)
    notes          = Column(String(255), default="")
    created_at     = Column(DateTime, default=datetime.utcnow)
    __table_args__ = (UniqueConstraint("store_id", "batch_ref"),)

    @property
    def transfers_total(self) -> float:
        """Sum of what the ACH actually debits: send amount + federal
        tax. The store fee stays with the store, so it's excluded from
        this total."""
        # Lazy import to avoid Transfer ↔ ACHBatch module-import cycle.
        from api.Modules.Transfers.Models import Transfer
        s = Session.object_session(self)
        if s is None:
            return 0.0
        v = (s.query(
                func.coalesce(func.sum(Transfer.send_amount), 0.0)
              + func.coalesce(func.sum(Transfer.federal_tax), 0.0))
             .filter_by(store_id=self.store_id, batch_id=self.batch_ref)
             .filter(Transfer.status != "Cancelled")
             .scalar())
        return float(v or 0.0)

    @property
    def variance(self) -> float:
        return round(float(self.ach_amount) - self.transfers_total, 2)

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
