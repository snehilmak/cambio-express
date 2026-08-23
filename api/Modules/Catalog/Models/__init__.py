"""Catalog — Models.

The price book + vendors foundation (P2-1, HANDOFF.md §2). Where
DayClose captures what SOLD, Catalog captures what the store
SELLS: the items on the shelves and the vendors that supply them.
Both tables are operator-owned catalogs per the pivot's product
principle — the operator names their world, we never hardcode it.

* ``Vendor``        — a supplier the store buys from (beer
                      distributor, grocery wholesaler, the lottery
                      commission…). Purchase invoices (Phase 2+)
                      will hang off these rows.
* ``PriceBookItem`` — one sellable item: scan code (UPC or keyed
                      PLU), name, retail price, cost, department +
                      vendor links. ``source`` records provenance —
                      "manual" (keyed by the operator) or
                      "gilbarco" (seeded from register journal
                      data by the warm-start import).

Money is integer cents from day one (P0-3 convention) — no Float
columns in this module, ever.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger, Boolean, Column, DateTime, ForeignKey, Integer,
    String, UniqueConstraint,
)
from sqlalchemy.orm import relationship

from api.Core.Database import Base
from api.Core.Money import DollarView

# POSCode formats we accept — matches the NAXML vocabulary the
# Gilbarco ingest already parses, so warm-started items round-trip.
POS_CODE_FORMATS = ("upc", "plu")


class Vendor(Base):
    __tablename__ = "vendor"
    id             = Column(Integer, primary_key=True)
    store_id       = Column(Integer, ForeignKey("store.id"), nullable=False, index=True)
    name           = Column(String(120), nullable=False)
    contact_name   = Column(String(120), nullable=False, default="")
    phone          = Column(String(30), nullable=False, default="")
    email          = Column(String(200), nullable=False, default="")
    # The store's account number WITH the vendor — printed on
    # invoices, needed when calling in orders.
    account_number = Column(String(60), nullable=False, default="")
    notes          = Column(String(500), nullable=False, default="")
    # Deactivate instead of delete — items + future purchase
    # invoices keep their FK when a vendor relationship ends.
    is_active      = Column(Boolean, default=True, nullable=False)
    created_at     = Column(DateTime, default=datetime.utcnow)
    __table_args__ = (UniqueConstraint("store_id", "name"),)


class PriceBookItem(Base):
    __tablename__ = "price_book_item"
    id              = Column(Integer, primary_key=True)
    store_id        = Column(Integer, ForeignKey("store.id"), nullable=False, index=True)
    # The scan code as the register knows it — UPC digits, or a
    # short keyed PLU ("2" = ice bag). Stored as a string so
    # leading zeros survive.
    pos_code        = Column(String(30), nullable=False)
    pos_code_format = Column(String(10), nullable=False, default="upc")
    name            = Column(String(160), nullable=False)
    department_id   = Column(
        Integer, ForeignKey("department.id"), nullable=True, index=True,
    )
    vendor_id       = Column(
        Integer, ForeignKey("vendor.id"), nullable=True, index=True,
    )
    price_cents     = Column(BigInteger, nullable=False, default=0)
    cost_cents      = Column(BigInteger, nullable=False, default=0)
    price           = DollarView("price_cents")
    cost            = DollarView("cost_cents")
    is_taxable      = Column(Boolean, default=True, nullable=False)
    is_active       = Column(Boolean, default=True, nullable=False)
    # Provenance: "manual" or an import source like "gilbarco".
    # Display only — imported items stay editable like any other.
    source          = Column(String(20), nullable=False, default="manual")
    created_at      = Column(DateTime, default=datetime.utcnow)
    updated_at      = Column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow,
    )
    __table_args__ = (UniqueConstraint("store_id", "pos_code"),)

    department = relationship("Department")
    vendor     = relationship("Vendor")


__all__ = ["POS_CODE_FORMATS", "PriceBookItem", "Vendor"]
