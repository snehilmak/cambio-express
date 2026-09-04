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
    BigInteger, Column, Date, DateTime, ForeignKey, Integer, String,
    Text, Time, UniqueConstraint,
)

from api.Core.Database import Base
from api.Core.Money import DollarView, to_dollars


class DailyReport(Base):
    __tablename__ = "msb_daily_report"
    id                    = Column(Integer, primary_key=True)
    store_id              = Column(Integer, ForeignKey("tenancy_store.id"), nullable=False)
    report_date           = Column(Date, nullable=False)
    taxable_sales_cents   = Column(BigInteger, default=0)
    non_taxable_cents     = Column(BigInteger, default=0)
    sales_tax_cents       = Column(BigInteger, default=0)
    bill_payment_charge_cents = Column(BigInteger, default=0)
    phone_recargas_cents  = Column(BigInteger, default=0)
    boost_mobile_cents    = Column(BigInteger, default=0)
    money_transfer_cents  = Column(BigInteger, default=0)
    money_order_cents     = Column(BigInteger, default=0)
    money_order_fees_cents = Column(BigInteger, default=0)
    check_cashing_fees_cents = Column(BigInteger, default=0)
    return_check_hold_fees_cents = Column(BigInteger, default=0)
    return_check_paid_back_cents = Column(BigInteger, default=0)
    forward_balance_cents = Column(BigInteger, default=0)
    # Operator override of the auto-carried opening balance (M-1).
    # NULL = follow the carry, which is the normal case. A value
    # PINS the day's opening cash: the carry is still computed and
    # shown beside it, so a chain that has diverged is visible
    # rather than silently ignored. Overriding one day never
    # cascades — tomorrow's carry reads that day's drops + safe, not
    # its forward balance.
    forward_balance_override_cents = Column(BigInteger, nullable=True)
    from_bank_cents       = Column(BigInteger, default=0)
    other_cash_in_cents   = Column(BigInteger, default=0)
    rebates_commissions_cents = Column(BigInteger, default=0)
    cash_purchases_cents  = Column(BigInteger, default=0)
    cash_expense_cents    = Column(BigInteger, default=0)
    check_purchases_cents = Column(BigInteger, default=0)
    check_expense_cents   = Column(BigInteger, default=0)
    outside_cash_drops_cents = Column(BigInteger, default=0)
    cash_deposit_cents    = Column(BigInteger, default=0)
    checks_deposit_cents  = Column(BigInteger, default=0)
    safe_balance_cents    = Column(BigInteger, default=0)
    payroll_expense_cents = Column(BigInteger, default=0)
    # Check payroll — line-item-derived (kind='payroll_check').
    # Deliberately NOT in total_disbursements or over_short: a
    # payroll check doesn't move drawer cash. Exists to feed the
    # monthly P&L's check-payroll line only.
    payroll_check_cents   = Column(BigInteger, default=0)
    other_cash_out_cents  = Column(BigInteger, default=0)
    over_short_cents      = Column(BigInteger, default=0)
    notes                 = Column(Text, default="")
    updated_at            = Column(DateTime, default=datetime.utcnow)
    # Lock state. When ``locked_at`` is not None every write to this
    # report (and its line items — drops, check deposits,
    # DailyLineItem rows) is rejected server-side. The user has to
    # explicitly unlock before editing again. ``locked_by`` is the
    # admin who set the lock.
    locked_at             = Column(DateTime, nullable=True)
    locked_by             = Column(Integer, ForeignKey("tenancy_user.id"), nullable=True)
    __table_args__ = (UniqueConstraint("store_id", "report_date"),)

    # Money is stored as INTEGER CENTS (P0-3; see api/Core/Money.py).
    # Each dollar-named DollarView reads/writes dollars over its
    # _cents column, so Python call sites and ORM kwargs keep their
    # dollars contract; SQL expressions must use _cents explicitly.
    taxable_sales = DollarView("taxable_sales_cents")
    non_taxable = DollarView("non_taxable_cents")
    sales_tax = DollarView("sales_tax_cents")
    bill_payment_charge = DollarView("bill_payment_charge_cents")
    phone_recargas = DollarView("phone_recargas_cents")
    boost_mobile = DollarView("boost_mobile_cents")
    money_transfer = DollarView("money_transfer_cents")
    money_order = DollarView("money_order_cents")
    money_order_fees = DollarView("money_order_fees_cents")
    check_cashing_fees = DollarView("check_cashing_fees_cents")
    return_check_hold_fees = DollarView("return_check_hold_fees_cents")
    return_check_paid_back = DollarView("return_check_paid_back_cents")
    forward_balance = DollarView("forward_balance_cents")
    from_bank = DollarView("from_bank_cents")
    other_cash_in = DollarView("other_cash_in_cents")
    rebates_commissions = DollarView("rebates_commissions_cents")
    cash_purchases = DollarView("cash_purchases_cents")
    cash_expense = DollarView("cash_expense_cents")
    check_purchases = DollarView("check_purchases_cents")
    check_expense = DollarView("check_expense_cents")
    outside_cash_drops = DollarView("outside_cash_drops_cents")
    cash_deposit = DollarView("cash_deposit_cents")
    checks_deposit = DollarView("checks_deposit_cents")
    safe_balance = DollarView("safe_balance_cents")
    payroll_expense = DollarView("payroll_expense_cents")
    payroll_check = DollarView("payroll_check_cents")
    other_cash_out = DollarView("other_cash_out_cents")
    over_short = DollarView("over_short_cents")

    @property
    def total_receipts_cents(self) -> int:
        return int(sum(int(v or 0) for v in [
            self.taxable_sales_cents, self.non_taxable_cents,
            self.sales_tax_cents, self.bill_payment_charge_cents,
            self.phone_recargas_cents, self.boost_mobile_cents,
            self.money_transfer_cents, self.money_order_cents,
            self.money_order_fees_cents, self.check_cashing_fees_cents,
            self.return_check_hold_fees_cents,
            self.return_check_paid_back_cents, self.forward_balance_cents,
            self.from_bank_cents, self.other_cash_in_cents,
            self.rebates_commissions_cents,
        ]))

    @property
    def total_receipts(self) -> float:
        return to_dollars(self.total_receipts_cents)

    @property
    def total_disbursements_cents(self) -> int:
        return int(sum(int(v or 0) for v in [
            self.cash_purchases_cents, self.cash_expense_cents,
            self.check_purchases_cents, self.check_expense_cents,
            self.outside_cash_drops_cents, self.cash_deposit_cents,
            self.checks_deposit_cents, self.payroll_expense_cents,
            self.other_cash_out_cents,
        ]))

    @property
    def total_disbursements(self) -> float:
        return to_dollars(self.total_disbursements_cents)

    @property
    def computed_over_short(self) -> float:
        """The day's cash-drawer reconciliation — the ``over_short``
        column is populated from this, never typed by the operator.

        Mirrors the master spreadsheet's "Over All Over-(Short)" =
        Total Payouts − Total Receipts, expressed as a pure CASH
        reconciliation:

            over_short = total_disbursements
                       − check_purchases − check_expense   (non-cash)
                       + safe_balance                       (cash kept)
                       − total_receipts

        Check purchases / expenses are paid by check, so they don't
        move the cash drawer and are excluded. ``safe_balance`` is
        cash retained overnight, so it counts as "paid out" for the
        reconciliation (it becomes tomorrow's opening ``forward_balance``
        via ``carry_forward_from``). Positive = OVER (surplus cash),
        negative = SHORT (a miscount or data-entry error — the books
        say more cash should be on hand than there is). See
        ``INVARIANTS.md`` → "Over/Short is derived".
        """
        return to_dollars(self.computed_over_short_cents)

    @property
    def computed_over_short_cents(self) -> int:
        return int(
            self.total_disbursements_cents
            - int(self.check_purchases_cents or 0)
            - int(self.check_expense_cents or 0)
            + int(self.safe_balance_cents or 0)
            - self.total_receipts_cents
        )


class DailyDrop(Base):
    """Individual "Outside Cash & Drop" entry — logged as they happen
    by time and amount, then summed into ``DailyReport.outside_cash_drops``.

    Mirrors the Drops section of the master spreadsheet: the main
    daily-book field becomes read-only, recomputed from these line
    items on every add / delete / daily-report save so the two always
    agree.
    """

    __tablename__ = "msb_daily_drop"
    id          = Column(Integer, primary_key=True)
    store_id    = Column(Integer, ForeignKey("tenancy_store.id"), nullable=False, index=True)
    report_date = Column(Date, nullable=False)
    drop_time   = Column(Time, nullable=False)
    amount_cents = Column(BigInteger, nullable=False, default=0)
    amount      = DollarView("amount_cents")
    note        = Column(String(120), default="")
    created_by  = Column(Integer, ForeignKey("tenancy_user.id"), nullable=True)
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

    __tablename__ = "msb_check_deposit"
    id           = Column(Integer, primary_key=True)
    store_id     = Column(Integer, ForeignKey("tenancy_store.id"), nullable=False, index=True)
    report_date  = Column(Date, nullable=False)
    deposit_time = Column(Time, nullable=False)
    amount_cents = Column(BigInteger, nullable=False, default=0)
    amount       = DollarView("amount_cents")
    note         = Column(String(120), default="")
    created_by   = Column(Integer, ForeignKey("tenancy_user.id"), nullable=True)
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

    __tablename__ = "msb_daily_line_item"
    id          = Column(Integer, primary_key=True)
    store_id    = Column(Integer, ForeignKey("tenancy_store.id"), nullable=False, index=True)
    report_date = Column(Date, nullable=False)
    # One of the keys in ``_LINE_ITEM_KINDS``. Not a DB enum so new
    # kinds can be introduced with zero migration.
    kind        = Column(String(40), nullable=False, index=True)
    at_time     = Column(Time, nullable=True)
    amount_cents = Column(BigInteger, nullable=False, default=0)
    amount      = DollarView("amount_cents")
    note        = Column(String(120), default="")
    # When this line item was auto-created by marking a ReturnCheck as
    # recovered, this FK links back to the source ReturnCheck. Lets us
    # find + update + delete the shadow line item when the return
    # check is edited or reopened, instead of leaving stale rows
    # behind. NULL for line items the cashier added manually.
    return_check_id = Column(Integer, ForeignKey("msb_return_check.id"),
                              nullable=True)
    created_by  = Column(Integer, ForeignKey("tenancy_user.id"), nullable=True)
    created_at  = Column(DateTime, default=datetime.utcnow)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "time": self.at_time.strftime("%H:%M") if self.at_time else "",
            "amount": float(self.amount or 0),
            "note": self.note or "",
        }


class MoneyTransferSummary(Base):
    __tablename__ = "msb_mt_summary"
    id           = Column(Integer, primary_key=True)
    store_id     = Column(Integer, ForeignKey("tenancy_store.id"), nullable=False)
    report_date  = Column(Date, nullable=False)
    company      = Column(String(40), nullable=False)
    amount_cents      = Column(BigInteger, default=0)
    fees_cents        = Column(BigInteger, default=0)
    commission_cents  = Column(BigInteger, default=0)
    # Federal tax collected from the customer on this company's
    # transfers for the day. Tracked separately from fees because
    # tax leaves with the ACH withdrawal, not store revenue.
    federal_tax_cents = Column(BigInteger, default=0)
    amount      = DollarView("amount_cents")
    fees        = DollarView("fees_cents")
    commission  = DollarView("commission_cents")
    federal_tax = DollarView("federal_tax_cents")
    __table_args__ = (UniqueConstraint("store_id", "report_date", "company"),)

    @property
    def individual_total_cents(self) -> int:
        return int((self.amount_cents or 0) + (self.fees_cents or 0)
                   + (self.commission_cents or 0)
                   + (self.federal_tax_cents or 0))

    @property
    def individual_total(self) -> float:
        return to_dollars(self.individual_total_cents)


# Re-export sibling models the DailyBook services touch.
from api.Modules.Tenancy.Models import Store, User  # noqa: E402


__all__ = [
    "CheckDeposit", "DailyDrop", "DailyLineItem", "DailyReport",
    "MoneyTransferSummary", "Store", "User",
]
