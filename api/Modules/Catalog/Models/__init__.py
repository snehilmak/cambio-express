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
    BigInteger, Boolean, Column, Date, DateTime, Float, ForeignKey,
    Integer, String, UniqueConstraint,
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
    # Item-editor parity phase 1 (P2-5). item_number = the vendor's
    # ordering number as printed on invoices; size = pack/size label
    # ("12oz", "POUND"). Case fields power the unit-cost derivation
    # (case_cost / case_size, displayed at 4 decimals client-side —
    # cost_cents stays the rounded stored value the rollups use).
    item_number     = Column(String(40), nullable=False, default="")
    size            = Column(String(40), nullable=False, default="")
    case_size       = Column(Integer, nullable=True)
    case_cost_cents = Column(BigInteger, nullable=True)
    case_cost       = DollarView("case_cost_cents")
    # EBT/SNAP-eligible — feeds labels/exports; the POS is still the
    # enforcement point until POS integration lands.
    is_ebt          = Column(Boolean, default=False, nullable=False)
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


# Invoice lifecycle. Not a DB enum so a future state ("disputed",
# "credited") lands without a migration.
INVOICE_STATUSES = ("open", "paid")


class PurchaseInvoice(Base):
    __tablename__ = "purchase_invoice"
    id             = Column(Integer, primary_key=True)
    store_id       = Column(Integer, ForeignKey("store.id"), nullable=False, index=True)
    vendor_id      = Column(
        Integer, ForeignKey("vendor.id"), nullable=False, index=True,
    )
    # The vendor's invoice number as printed — the key the operator
    # reconciles statements against. Unique per (store, vendor):
    # different vendors reuse the same numbering ranges.
    invoice_number = Column(String(60), nullable=False)
    invoice_date   = Column(Date, nullable=False)
    due_date       = Column(Date, nullable=True)
    subtotal_cents = Column(BigInteger, nullable=False, default=0)
    tax_cents      = Column(BigInteger, nullable=False, default=0)
    # Freight, deposits, CRV, misc surcharges — anything on the
    # paper that isn't merchandise or tax.
    other_cents    = Column(BigInteger, nullable=False, default=0)
    subtotal = DollarView("subtotal_cents")
    tax      = DollarView("tax_cents")
    other    = DollarView("other_cents")
    status   = Column(String(16), nullable=False, default="open")
    paid_on  = Column(Date, nullable=True)
    notes      = Column(String(500), nullable=False, default="")
    created_by = Column(Integer, ForeignKey("user.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow,
    )
    __table_args__ = (
        UniqueConstraint("store_id", "vendor_id", "invoice_number"),
    )

    vendor = relationship("Vendor")
    lines  = relationship(
        "PurchaseInvoiceLine", backref="invoice",
        cascade="all, delete-orphan",
    )

    @property
    def total_cents(self) -> int:
        """Invoice total — derived, never stored (subtotal + tax +
        other). Line items are supporting detail: their sum is NOT
        forced to equal the subtotal (partial line entry is fine —
        variance is surfaced, never blocked)."""
        return (
            int(self.subtotal_cents or 0)
            + int(self.tax_cents or 0)
            + int(self.other_cents or 0)
        )


class PurchaseInvoiceLine(Base):
    __tablename__ = "purchase_invoice_line"
    id         = Column(Integer, primary_key=True)
    store_id   = Column(Integer, ForeignKey("store.id"), nullable=False, index=True)
    invoice_id = Column(
        Integer, ForeignKey("purchase_invoice.id"), nullable=False, index=True,
    )
    # Optional price-book link — misc lines (ice bags of CO2, a
    # one-off charge) have no catalog item.
    item_id     = Column(
        Integer, ForeignKey("price_book_item.id"), nullable=True, index=True,
    )
    description = Column(String(160), nullable=False, default="")
    # Quantity can be fractional (weighted goods, split cases) —
    # Float like gallons/hourly_rate: a measure, not money.
    quantity        = Column(Float, nullable=False, default=1.0)
    unit_cost_cents = Column(BigInteger, nullable=False, default=0)
    unit_cost       = DollarView("unit_cost_cents")
    # Stored (not derived) so the operator can key the printed
    # extended amount even when it rounds differently than
    # quantity × unit cost.
    line_total_cents = Column(BigInteger, nullable=False, default=0)
    line_total       = DollarView("line_total_cents")

    item = relationship("PriceBookItem")


__all__ = [
    "INVOICE_STATUSES", "POS_CODE_FORMATS", "PriceBookItem",
    "PurchaseInvoice", "PurchaseInvoiceLine", "Vendor",
]
