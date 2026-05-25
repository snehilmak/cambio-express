"""DailyBook — Models.

Five classes that own the per-day close-out book:

* ``DailyReport``         — the per-day P&L stub. One row per
                             (store, date) with column-totals for
                             receipts, disbursements, drops, etc.
* ``DailyDrop``           — individual "Outside Cash & Drop" event;
                             rolls up into ``outside_cash_drops``.
* ``CheckDeposit``        — individual check deposit; rolls up into
                             ``checks_deposit``.
* ``DailyLineItem``       — generic time-amount-note line item keyed
                             by ``kind`` (replaces bespoke per-line
                             tables for cash purchases, expenses,
                             etc.).
* ``MoneyTransferSummary`` — per-company per-day MT roll-up.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    Column, Date, DateTime, Float, ForeignKey, Integer, String, Text,
    Time, UniqueConstraint,
)

from api.Core.Database import Base


class DailyReport(Base):
    __tablename__ = "daily_report"
    id                    = Column(Integer, primary_key=True)
    store_id              = Column(Integer, ForeignKey("store.id"), nullable=False)
    report_date           = Column(Date, nullable=False)
    taxable_sales         = Column(Float, default=0.0)
    non_taxable           = Column(Float, default=0.0)
    sales_tax             = Column(Float, default=0.0)
    bill_payment_charge   = Column(Float, default=0.0)
    phone_recargas        = Column(Float, default=0.0)
    boost_mobile          = Column(Float, default=0.0)
    money_transfer        = Column(Float, default=0.0)
    money_order           = Column(Float, default=0.0)
    check_cashing_fees    = Column(Float, default=0.0)
    return_check_hold_fees= Column(Float, default=0.0)
    return_check_paid_back= Column(Float, default=0.0)
    forward_balance       = Column(Float, default=0.0)
    from_bank             = Column(Float, default=0.0)
    other_cash_in         = Column(Float, default=0.0)
    rebates_commissions   = Column(Float, default=0.0)
    cash_purchases        = Column(Float, default=0.0)
    cash_expense          = Column(Float, default=0.0)
    check_purchases       = Column(Float, default=0.0)
    check_expense         = Column(Float, default=0.0)
    outside_cash_drops    = Column(Float, default=0.0)
    cash_deposit          = Column(Float, default=0.0)
    checks_deposit        = Column(Float, default=0.0)
    safe_balance          = Column(Float, default=0.0)
    payroll_expense       = Column(Float, default=0.0)
    other_cash_out        = Column(Float, default=0.0)
    over_short            = Column(Float, default=0.0)
    notes                 = Column(Text, default="")
    updated_at            = Column(DateTime, default=datetime.utcnow)
    # Lock state. When ``locked_at`` is not None every write to this
    # report (and its line items — drops, check deposits,
    # DailyLineItem rows) is rejected server-side. The user has to
    # explicitly unlock before editing again. ``locked_by`` is the
    # admin who set the lock.
    locked_at             = Column(DateTime, nullable=True)
    locked_by             = Column(Integer, ForeignKey("user.id"), nullable=True)
    __table_args__ = (UniqueConstraint("store_id", "report_date"),)

    @property
    def total_receipts(self) -> float:
        return float(sum([
            self.taxable_sales, self.non_taxable, self.sales_tax,
            self.bill_payment_charge, self.phone_recargas,
            self.boost_mobile, self.money_transfer, self.money_order,
            self.check_cashing_fees, self.return_check_hold_fees,
            self.return_check_paid_back, self.forward_balance,
            self.from_bank, self.other_cash_in, self.rebates_commissions,
        ]))

    @property
    def total_disbursements(self) -> float:
        return float(sum([
            self.cash_purchases, self.cash_expense, self.check_purchases,
            self.check_expense, self.outside_cash_drops, self.cash_deposit,
            self.checks_deposit, self.payroll_expense, self.other_cash_out,
        ]))


class DailyDrop(Base):
    """Individual "Outside Cash & Drop" entry — logged as they happen
    by time and amount, then summed into ``DailyReport.outside_cash_drops``.

    Mirrors the Drops section of the master spreadsheet: the main
    daily-book field becomes read-only, recomputed from these line
    items on every add / delete / daily-report save so the two always
    agree.
    """

    __tablename__ = "daily_drop"
    id          = Column(Integer, primary_key=True)
    store_id    = Column(Integer, ForeignKey("store.id"), nullable=False, index=True)
    report_date = Column(Date, nullable=False)
    drop_time   = Column(Time, nullable=False)
    amount      = Column(Float, nullable=False)
    note        = Column(String(120), default="")
    created_by  = Column(Integer, ForeignKey("user.id"), nullable=True)
    created_at  = Column(DateTime, default=datetime.utcnow)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "time": self.drop_time.strftime("%H:%M") if self.drop_time else "",
            "amount": float(self.amount or 0),
            "note": self.note or "",
        }


class CheckDeposit(Base):
    """Individual check-deposit entry — logged as it happens by time
    and amount, then summed into ``DailyReport.checks_deposit``.

    Same shape as ``DailyDrop``: a store can record multiple check
    deposits across a single day (e.g. morning run + afternoon run),
    and the daily-book's Checks Deposit line becomes a read-only sum
    of these rows. The server recomputes from ``CheckDeposit`` on
    every add / delete / daily-report save so the two can never drift.
    """

    __tablename__ = "check_deposit"
    id           = Column(Integer, primary_key=True)
    store_id     = Column(Integer, ForeignKey("store.id"), nullable=False, index=True)
    report_date  = Column(Date, nullable=False)
    deposit_time = Column(Time, nullable=False)
    amount       = Column(Float, nullable=False)
    note         = Column(String(120), default="")
    created_by   = Column(Integer, ForeignKey("user.id"), nullable=True)
    created_at   = Column(DateTime, default=datetime.utcnow)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "time": self.deposit_time.strftime("%H:%M") if self.deposit_time else "",
            "amount": float(self.amount or 0),
            "note": self.note or "",
        }


class DailyLineItem(Base):
    """Generic time-amount-note line item that rolls up into a single
    DailyReport field, discriminated by ``kind``.

    Covers the daily-book lines that a real store may log multiple
    times per day (e.g. cash purchases, cash expenses, check
    purchases, check expenses, return-check paybacks). Each kind maps
    to exactly one DailyReport field (see ``_LINE_ITEM_KINDS`` in
    app.py), and the field becomes read-only — the server always
    re-derives the total from these rows on save so a stale form
    can't overwrite it.

    ``DailyDrop`` and ``CheckDeposit`` kept their bespoke tables from
    before this was introduced; they behave identically but predate
    the generic model.
    """

    __tablename__ = "daily_line_item"
    id          = Column(Integer, primary_key=True)
    store_id    = Column(Integer, ForeignKey("store.id"), nullable=False, index=True)
    report_date = Column(Date, nullable=False)
    # One of the keys in ``_LINE_ITEM_KINDS``. Not a DB enum so new
    # kinds can be introduced with zero migration.
    kind        = Column(String(40), nullable=False, index=True)
    at_time     = Column(Time, nullable=True)
    amount      = Column(Float, nullable=False)
    note        = Column(String(120), default="")
    # When this line item was auto-created by marking a ReturnCheck as
    # recovered, this FK links back to the source ReturnCheck. Lets us
    # find + update + delete the shadow line item when the return
    # check is edited or reopened, instead of leaving stale rows
    # behind. NULL for line items the cashier added manually.
    return_check_id = Column(Integer, ForeignKey("return_check.id"),
                              nullable=True)
    created_by  = Column(Integer, ForeignKey("user.id"), nullable=True)
    created_at  = Column(DateTime, default=datetime.utcnow)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "time": self.at_time.strftime("%H:%M") if self.at_time else "",
            "amount": float(self.amount or 0),
            "note": self.note or "",
        }


class MoneyTransferSummary(Base):
    __tablename__ = "mt_summary"
    id           = Column(Integer, primary_key=True)
    store_id     = Column(Integer, ForeignKey("store.id"), nullable=False)
    report_date  = Column(Date, nullable=False)
    company      = Column(String(40), nullable=False)
    amount       = Column(Float, default=0.0)
    fees         = Column(Float, default=0.0)
    commission   = Column(Float, default=0.0)
    # Federal tax collected from the customer on this company's
    # transfers for the day. Tracked separately from fees because
    # tax leaves with the ACH withdrawal, not store revenue.
    federal_tax  = Column(Float, default=0.0)
    __table_args__ = (UniqueConstraint("store_id", "report_date", "company"),)

    @property
    def individual_total(self) -> float:
        return float((self.amount or 0) + (self.fees or 0)
                     + (self.commission or 0) + (self.federal_tax or 0))


# Re-export sibling models the DailyBook services touch.
from api.Modules.Tenancy.Models import Store, User  # noqa: E402


__all__ = [
    "CheckDeposit", "DailyDrop", "DailyLineItem", "DailyReport",
    "MoneyTransferSummary", "Store", "User",
]
