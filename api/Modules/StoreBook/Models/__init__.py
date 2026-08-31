"""StoreBook — Models.

``StoreDailyEntry`` is one store's business day. Money is integer
cents throughout (P0-3), exposed as dollars through ``DollarView``
like every other ledger in the app.

The field list mirrors what a c-store operator actually closes out
against, grouped by the three columns of the page. Adding a field
means: column here, entry in ``FIELD_GROUPS`` (which drives both
the API contract and the page layout), and a migration.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger, Column, Date, DateTime, Float, ForeignKey, Integer,
    String, Text, UniqueConstraint,
)
from sqlalchemy.orm import relationship

from api.Core.Database import Base
from api.Core.Money import DollarView


# Every money field on the sheet, grouped the way the page renders
# them: column → section → fields. This is the single source of
# truth for the layout, the API payload and the totals math —
# the SPA reads it rather than hard-coding its own copy, so a new
# field appears in both places or neither.
#
# `count_field` marks the paired "# / $" inputs the screenshots use
# for money orders, transfers, bill pay, ATM withdrawals and
# coupons: a count next to an amount, both meaningful.
FIELD_GROUPS: list[dict] = [
    {
        "column": "sales",
        "label": "Sales",
        "sections": [
            {"key": "opening_balance", "label": "Opening balance", "fields": [
                {"key": "opening_balance", "label": "Opening balance"},
            ]},
            {"key": "cash_in", "label": "Cash in", "fields": [
                {"key": "cash_in", "label": "Cash in"},
                {"key": "money_from_banks", "label": "Money from banks"},
            ]},
            {"key": "sales", "label": "Sales", "fields": [
                {"key": "taxable_sales", "label": "Taxable"},
                {"key": "non_taxable_sales", "label": "Non tax"},
                {"key": "gross_sales", "label": "Gross sales"},
                {"key": "sales_tax", "label": "Sales tax"},
            ]},
            {"key": "lottery", "label": "Lottery", "fields": [
                {"key": "lottery_sales", "label": "Lottery sales"},
                {"key": "lotto_sales", "label": "Lotto sales"},
                {"key": "lotto_adjustment", "label": "Lotto adjustment"},
                {"key": "lottery_credits", "label": "Lottery credits"},
            ]},
            {"key": "rebates_income", "label": "Rebates / income", "fields": [
                {"key": "check_income", "label": "Check income"},
                {"key": "check_rebate", "label": "Check rebate"},
                {"key": "equity", "label": "Equity"},
                {"key": "loan", "label": "Loan"},
            ]},
            {"key": "money_order", "label": "Money order", "fields": [
                {"key": "money_order", "label": "Money order",
                 "count_field": "money_order_count"},
            ]},
            {"key": "phone_card", "label": "Phone card", "fields": [
                {"key": "phone_card", "label": "Phone card"},
            ]},
            {"key": "fuel_sales", "label": "Fuel sales", "fields": [
                {"key": "fuel_amount", "label": "Amount",
                 "gallons_field": "fuel_gallons"},
            ]},
            {"key": "check_fees", "label": "Check fees", "fields": [
                {"key": "check_fees", "label": "Check fees"},
            ]},
            {"key": "money_transfer", "label": "Money transfer", "fields": [
                {"key": "money_transfer", "label": "Money transfer",
                 "count_field": "money_transfer_count"},
            ]},
            {"key": "account_receivable", "label": "Account receivable",
             "fields": [
                {"key": "ac_received", "label": "A/C received"},
            ]},
            {"key": "bill_pay", "label": "Bill pay", "fields": [
                {"key": "bill_pay", "label": "Bill pay",
                 "count_field": "bill_pay_count"},
            ]},
        ],
    },
    {
        "column": "tenders",
        "label": "Tenders",
        "sections": [
            {"key": "checks", "label": "Checks", "fields": [
                {"key": "checks", "label": "Checks"},
            ]},
            {"key": "closing_cash", "label": "Closing cash", "fields": [
                {"key": "closing_cash", "label": "Closing cash"},
            ]},
            {"key": "cash_out", "label": "Cash out", "fields": [
                {"key": "cash_out", "label": "Cash out"},
            ]},
            {"key": "gas_pos_cards", "label": "Gas POS cards", "fields": [
                {"key": "gas_pos_cards", "label": "Gas POS cards"},
            ]},
            {"key": "lotto_po", "label": "Lotto PO", "fields": [
                {"key": "lotto_paid_out", "label": "Lotto / lottery PO"},
            ]},
            {"key": "customer_credit", "label": "Customer credit", "fields": [
                {"key": "customer_credit", "label": "Customer credit"},
            ]},
            {"key": "cards", "label": "Cards", "fields": [
                {"key": "cards", "label": "Cards"},
                {"key": "store_credit", "label": "Store credit"},
            ]},
            {"key": "coupon", "label": "Coupon", "fields": [
                {"key": "coupon_amount", "label": "Coupon amount",
                 "count_field": "coupon_count"},
            ]},
            {"key": "loyalty", "label": "Loyalty", "fields": [
                {"key": "loyalty", "label": "Loyalty"},
            ]},
            {"key": "paid_out", "label": "Paid out", "fields": [
                {"key": "paid_out_expenses", "label": "Expenses"},
                {"key": "paid_out_purchases", "label": "Purchases"},
                {"key": "paid_out_advance", "label": "Advance"},
            ]},
            {"key": "pre_deposits", "label": "Pre deposits", "fields": [
                {"key": "pre_cash_deposit", "label": "Pre cash deposit"},
                {"key": "pre_check_deposit", "label": "Pre check deposit"},
            ]},
            {"key": "atm", "label": "ATM", "fields": [
                {"key": "atm_loads", "label": "Loads"},
                {"key": "atm_withdrawal", "label": "Withdrawal",
                 "count_field": "atm_withdrawal_count"},
                {"key": "atm_fees", "label": "Total ATM fees"},
                {"key": "atm_rejected", "label": "Rejected bills",
                 "count_field": "atm_rejected_count"},
                {"key": "atm_balance", "label": "ATM balance"},
            ]},
        ],
    },
    {
        "column": "deposit",
        "label": "Deposit & balance",
        "sections": [
            {"key": "check_paid_out", "label": "Check paid out", "fields": [
                {"key": "check_paid_expenses", "label": "Expenses"},
                {"key": "check_paid_purchases", "label": "Purchases"},
                {"key": "check_paid_payroll", "label": "Payroll"},
            ]},
            {"key": "deposits", "label": "Deposits", "fields": [
                {"key": "cash_deposit", "label": "Cash deposit"},
                {"key": "check_deposit", "label": "Check deposit"},
                {"key": "eft_deposit", "label": "EFT deposit"},
                {"key": "merchant_deposit", "label": "Merchant deposit"},
                {"key": "income_rebate_equity",
                 "label": "Income / rebate / equity"},
                {"key": "atm_deposit", "label": "ATM deposit"},
            ]},
            {"key": "closing_balance", "label": "Closing balance", "fields": [
                {"key": "closing_balance", "label": "Closing balance"},
            ]},
        ],
    },
]


def _money_field_keys() -> list[str]:
    """Every ``*_cents`` money key, in page order."""
    keys: list[str] = []
    for column in FIELD_GROUPS:
        for section in column["sections"]:
            for field in section["fields"]:
                keys.append(field["key"])
    return keys


def _count_field_keys() -> list[str]:
    """The plain-integer companions (counts, gallons) — NOT money,
    so they never take part in the cents math."""
    keys: list[str] = []
    for column in FIELD_GROUPS:
        for section in column["sections"]:
            for field in section["fields"]:
                for extra in ("count_field", "gallons_field"):
                    if field.get(extra):
                        keys.append(field[extra])
    return keys


MONEY_FIELDS: tuple[str, ...] = tuple(_money_field_keys())
COUNT_FIELDS: tuple[str, ...] = tuple(_count_field_keys())

# Which column each money field belongs to — drives the three
# running totals in the page header.
FIELD_COLUMN: dict[str, str] = {
    field["key"]: column["column"]
    for column in FIELD_GROUPS
    for section in column["sections"]
    for field in section["fields"]
}


def _money(name: str) -> Column:
    return Column(BigInteger, nullable=False, default=0)


class StoreDailyEntry(Base):
    """One store's business day.

    Every money column is cents and defaults to 0 — a blank field
    on the page means zero, not "unknown", which is what makes the
    three column totals always computable.
    """

    __tablename__ = "store_daily_entry"
    id         = Column(Integer, primary_key=True)
    store_id   = Column(
        Integer, ForeignKey("store.id"), nullable=False, index=True,
    )
    entry_date = Column(Date, nullable=False, index=True)

    # ── Sales ──────────────────────────────────────────────
    opening_balance_cents     = _money("opening_balance")
    cash_in_cents             = _money("cash_in")
    money_from_banks_cents    = _money("money_from_banks")
    taxable_sales_cents       = _money("taxable_sales")
    non_taxable_sales_cents   = _money("non_taxable_sales")
    gross_sales_cents         = _money("gross_sales")
    sales_tax_cents           = _money("sales_tax")
    lottery_sales_cents       = _money("lottery_sales")
    lotto_sales_cents         = _money("lotto_sales")
    lotto_adjustment_cents    = _money("lotto_adjustment")
    lottery_credits_cents     = _money("lottery_credits")
    check_income_cents        = _money("check_income")
    check_rebate_cents        = _money("check_rebate")
    equity_cents              = _money("equity")
    loan_cents                = _money("loan")
    money_order_cents         = _money("money_order")
    phone_card_cents          = _money("phone_card")
    fuel_amount_cents         = _money("fuel_amount")
    check_fees_cents          = _money("check_fees")
    money_transfer_cents      = _money("money_transfer")
    ac_received_cents         = _money("ac_received")
    bill_pay_cents            = _money("bill_pay")

    # ── Tenders ────────────────────────────────────────────
    checks_cents              = _money("checks")
    closing_cash_cents        = _money("closing_cash")
    cash_out_cents            = _money("cash_out")
    gas_pos_cards_cents       = _money("gas_pos_cards")
    lotto_paid_out_cents      = _money("lotto_paid_out")
    customer_credit_cents     = _money("customer_credit")
    cards_cents               = _money("cards")
    store_credit_cents        = _money("store_credit")
    coupon_amount_cents       = _money("coupon_amount")
    loyalty_cents             = _money("loyalty")
    paid_out_expenses_cents   = _money("paid_out_expenses")
    paid_out_purchases_cents  = _money("paid_out_purchases")
    paid_out_advance_cents    = _money("paid_out_advance")
    pre_cash_deposit_cents    = _money("pre_cash_deposit")
    pre_check_deposit_cents   = _money("pre_check_deposit")
    atm_loads_cents           = _money("atm_loads")
    atm_withdrawal_cents      = _money("atm_withdrawal")
    atm_fees_cents            = _money("atm_fees")
    atm_rejected_cents        = _money("atm_rejected")
    atm_balance_cents         = _money("atm_balance")

    # ── Deposit & balance ──────────────────────────────────
    check_paid_expenses_cents  = _money("check_paid_expenses")
    check_paid_purchases_cents = _money("check_paid_purchases")
    check_paid_payroll_cents   = _money("check_paid_payroll")
    cash_deposit_cents         = _money("cash_deposit")
    check_deposit_cents        = _money("check_deposit")
    eft_deposit_cents          = _money("eft_deposit")
    merchant_deposit_cents     = _money("merchant_deposit")
    income_rebate_equity_cents = _money("income_rebate_equity")
    atm_deposit_cents          = _money("atm_deposit")
    closing_balance_cents      = _money("closing_balance")

    # ── Counts + volume (not money) ────────────────────────
    money_order_count      = Column(Integer, nullable=False, default=0)
    money_transfer_count   = Column(Integer, nullable=False, default=0)
    bill_pay_count         = Column(Integer, nullable=False, default=0)
    coupon_count           = Column(Integer, nullable=False, default=0)
    atm_withdrawal_count   = Column(Integer, nullable=False, default=0)
    atm_rejected_count     = Column(Integer, nullable=False, default=0)
    # Gallons is volume, not money — float, same rationale as the
    # fuel volumes in the POS import.
    fuel_gallons           = Column(Float, nullable=False, default=0.0)

    notes      = Column(Text, nullable=False, default="")
    updated_at = Column(DateTime, default=datetime.utcnow)
    # Lock, mirroring the MSB daily book: a locked day rejects
    # operator writes until an admin unlocks it. POS imports are
    # deliberately NOT blocked by the lock — see the Services
    # module for why.
    locked_at  = Column(DateTime, nullable=True)
    locked_by  = Column(Integer, ForeignKey("user.id"), nullable=True)

    __table_args__ = (
        UniqueConstraint("store_id", "entry_date"),
    )

    originals = relationship(
        "StoreDailyEntryOriginal", back_populates="entry",
        cascade="all, delete-orphan",
    )


# Dollar views for every money column, attached after the class
# body so the field list stays readable and can't drift from
# MONEY_FIELDS.
for _key in MONEY_FIELDS:
    setattr(StoreDailyEntry, _key, DollarView(f"{_key}_cents"))


class StoreDailyEntryOriginal(Base):
    """What the POS reported for one field, before any operator
    edit.

    The page shows this under the input as "Orig. Val", green when
    the operator's value still matches and red when they overrode
    it. Keeping it separate from the entry row means correcting a
    figure never destroys what the register actually said, and a
    re-import can restore it — the auditable version of "trust the
    ledger, not the stored value".

    One row per (entry, field) only for fields an import actually
    supplied; hand-entered fields have no original and render
    without the caption.
    """

    __tablename__ = "store_daily_entry_original"
    id       = Column(Integer, primary_key=True)
    entry_id = Column(
        Integer,
        ForeignKey("store_daily_entry.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    store_id     = Column(Integer, nullable=False, index=True)
    field_key    = Column(String(40), nullable=False)
    amount_cents = Column(BigInteger, nullable=False, default=0)
    # Where it came from — "gilbarco" today; a second POS later.
    source       = Column(String(20), nullable=False, default="")
    imported_at  = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("entry_id", "field_key"),
    )

    entry = relationship("StoreDailyEntry", back_populates="originals")


__all__ = [
    "COUNT_FIELDS", "FIELD_COLUMN", "FIELD_GROUPS", "MONEY_FIELDS",
    "StoreDailyEntry", "StoreDailyEntryOriginal",
]
