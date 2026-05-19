"""BankSync — Models.

Three classes that back the Stripe Financial Connections integration:

* ``StripeBankAccount`` — one row per connected bank account
                          (institution, last4, last-known balance).
* ``BankTransaction``   — cached transactions pulled from Stripe;
                          idempotent on ``stripe_transaction_id``.
* ``BankRule``          — operator-managed auto-categorization rule.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger, Boolean, Column, DateTime, ForeignKey, Index, Integer,
    String,
)

from api.Core.Database import Base


class StripeBankAccount(Base):
    """A bank account connected via Stripe Financial Connections.

    One row per connected account (a store may link several). We
    cache just enough metadata to render the UI — the institution
    name, last4, account type, and the last-known balance +
    timestamp. Balances refresh on demand (user clicks Refresh, or
    we pull in Account.refresh on page load when stale). Credentials
    are never held here — Stripe is the custodian.
    """

    __tablename__ = "stripe_bank_account"
    id                   = Column(Integer, primary_key=True)
    store_id             = Column(Integer, ForeignKey("store.id"), nullable=False, index=True)
    stripe_account_id    = Column(String(60), unique=True, nullable=False)
    institution_name     = Column(String(120), default="")
    display_name         = Column(String(120), default="")
    last4                = Column(String(8), default="")
    category             = Column(String(30), default="")   # checking / savings / credit / other
    subcategory          = Column(String(30), default="")
    currency             = Column(String(8), default="usd")
    last_balance_cents   = Column(BigInteger, default=0)
    last_balance_as_of   = Column(DateTime, nullable=True)
    connected_at         = Column(DateTime, default=datetime.utcnow)
    disconnected_at      = Column(DateTime, nullable=True)
    enabled              = Column(Boolean, default=True)
    # Operator-set nickname. When non-empty the transactions list +
    # P&L breakdown show this instead of "••<last4>".
    nickname             = Column(String(60), default="")

    @property
    def label(self) -> str:
        """Display label: nickname when set, else ••last4, else 'Account'."""
        if self.nickname:
            return str(self.nickname)
        if self.last4:
            return f"••{self.last4}"
        return "Account"

    @property
    def last_balance(self) -> float:
        return float((self.last_balance_cents or 0) / 100.0)


class BankTransaction(Base):
    """A transaction pulled from Stripe Financial Connections.

    Cached locally so we can render the daily list without re-hitting
    Stripe (each Transaction.list call is billed). Idempotent on
    ``stripe_transaction_id`` — re-syncing the same window safely
    no-ops rows we've already seen.

    The status field tracks Stripe's transaction lifecycle:
      pending  — visible but not yet posted to the bank ledger
      posted   — settled
      void     — reversed before posting

    ``category_slug`` is the daily-book line-item kind (one of
    ``_LINE_ITEM_KINDS``) OR a non-posting tag from
    ``BANK_CATEGORIES_NON_POSTING``. ``matched_rule_id`` is the
    BankRule that auto-categorized this row (null when set manually).
    When the category is a daily-book kind, ``daily_line_item_id``
    links to the DailyLineItem we created — un-reconcile deletes it.
    """

    __tablename__ = "bank_transaction"
    id                       = Column(Integer, primary_key=True)
    store_id                 = Column(Integer, ForeignKey("store.id"), nullable=False)
    stripe_bank_account_id   = Column(Integer, ForeignKey("stripe_bank_account.id"), nullable=False)
    stripe_transaction_id    = Column(String(80), unique=True, nullable=False)
    amount_cents             = Column(BigInteger, nullable=False)  # signed: + credit, - debit
    currency                 = Column(String(8), default="usd")
    description              = Column(String(500), default="")
    posted_at                = Column(DateTime, nullable=True)
    status                   = Column(String(20), default="posted")
    category_slug            = Column(String(60), default="")
    matched_rule_id          = Column(Integer, nullable=True)
    daily_line_item_id       = Column(Integer,
                                       ForeignKey("daily_line_item.id"),
                                       nullable=True)
    created_at               = Column(DateTime, default=datetime.utcnow)
    __table_args__ = (
        Index("ix_bank_transaction_store_posted",
              "store_id", "posted_at"),
    )

    @property
    def amount(self) -> float:
        return float((self.amount_cents or 0) / 100.0)


class BankRule(Base):
    """Operator-managed rule that auto-categorizes BankTransactions on
    sync.

    All match conditions are independently optional — a rule may be
    as minimal as "description contains EmagineNet" or as specific
    as "description contains EmagineNet AND amount = $180.00 AND
    debit on account ••0210". Lower priority numbers match first;
    the first matching enabled rule wins and stops further
    evaluation.

    Manual categorization on a transaction (via the UI) sets
    ``matched_rule_id=NULL`` — the rule is only credited when sync
    auto-applies it. This lets us count true automations.
    """

    __tablename__ = "bank_rule"
    id                  = Column(Integer, primary_key=True)
    store_id            = Column(Integer, ForeignKey("store.id"),
                                  nullable=False, index=True)
    enabled             = Column(Boolean, default=True)
    priority            = Column(Integer, default=100)

    # All four conditions optional. desc_match_type "" means "skip
    # description match"; if non-empty, desc_match_value is required.
    desc_match_type     = Column(String(20), default="")  # "" | contains | starts_with | equals | regex
    desc_match_value    = Column(String(500), default="")
    sign_filter         = Column(String(10), default="")  # "" | credit | debit
    amount_min_cents    = Column(Integer, nullable=True)  # absolute cents; None = unbounded
    amount_max_cents    = Column(Integer, nullable=True)
    account_filter_id   = Column(Integer,
                                  ForeignKey("stripe_bank_account.id"),
                                  nullable=True)

    # Output: a daily-book line-item kind from ``_LINE_ITEM_KINDS``,
    # OR a non-posting tag from ``BANK_CATEGORIES_NON_POSTING``.
    target_kind         = Column(String(40), nullable=False)
    auto_post           = Column(Boolean, default=True)

    description         = Column(String(200), default="")  # operator note
    match_count         = Column(Integer, default=0)
    last_matched_at     = Column(DateTime, nullable=True)
    created_at          = Column(DateTime, default=datetime.utcnow)
    updated_at          = Column(DateTime, default=datetime.utcnow,
                                  onupdate=datetime.utcnow)


# Re-export Store for existing
# ``from api.Modules.BankSync.Models import Store`` call sites.
from api.Modules.Tenancy.Models import Store  # noqa: E402


__all__ = ["BankRule", "BankTransaction", "Store", "StripeBankAccount"]
