"""ReturnChecks — Models.

Two classes that own the bounced-customer-check workflow:

* ``ReturnCheck``        — one row per bounced check. Status moves
                           pending → recovered / loss / fraud once,
                           landing the gain/loss on that month's P&L.
* ``ReturnCheckPayment`` — installments of repayment against a
                           parent ``ReturnCheck``. Each payment also
                           auto-creates a matching
                           ``DailyLineItem(kind='return_payback')``
                           via the route handler.

Status constants ``RETURN_CHECK_STATUSES`` and
``RETURN_CHECK_BOOKED`` live alongside the classes.
"""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    BigInteger, Column, Date, DateTime, ForeignKey, Integer, String, Text,
)
from sqlalchemy.orm import relationship

from api.Core.Database import Base
from api.Core.Money import to_cents, to_dollars


# Status values for ``ReturnCheck.status``. Kept as module-level
# constants so the route handlers, P&L aggregator, and tests all
# reference the same vocabulary.
RETURN_CHECK_STATUSES = ("pending", "recovered", "loss", "fraud")
RETURN_CHECK_BOOKED   = ("recovered", "loss", "fraud")  # i.e. closed; affect P&L


class ReturnCheck(Base):
    """A bounced customer check — the workflow lives entirely on this
    row, not split across multiple events.

    Why this exists: cashiers used to track bounced checks in a
    separate Excel tab, manually carrying pending items forward each
    month and writing the eventual gain or loss into the monthly
    P&L's "Return Check (G/L)" line by hand. We model the exact
    same workflow here:

      bounced_on   the date the check came back from the bank. Never
                   moves once set; it's the historical fact.

      status       'pending'   — sitting on the books, owner is
                                  still trying to recover
                   'recovered' — fully or partially repaid; the gain
                                  is the recovered_amount
                   'loss'      — written off; the entire ``amount``
                                  is the loss
                   'fraud'     — same accounting as 'loss', kept as
                                  a distinct status for reporting

      status_changed_on
                   the date status moved out of ``pending``. This is
                   what drives which month's P&L the gain/loss lands
                   on. A pending row never touches any month's P&L —
                   only marking it (recovered / loss / fraud) does.

      recovered_amount
                   only meaningful when status='recovered'. May be
                   less than ``amount`` (partial recovery); the
                   difference is the implicit shortfall the cashier
                   chose to accept. If they later mark the row 'loss'
                   instead, the FULL ``amount`` becomes the loss
                   (recovered_amount is reset).

    P&L formula for a given month (locked field on monthly_report):

        Σ recovered_amount where status='recovered'
                                AND status_changed_on in the month
      − Σ amount             where status in ('loss','fraud')
                                AND status_changed_on in the month

    Positive = net gain (recoveries beat write-offs); negative = net
    loss. Pending balance does NOT enter the P&L — it's a separate
    KPI on the list page and owner dashboard.
    """

    __tablename__ = "return_check"
    id              = Column(Integer, primary_key=True)
    store_id        = Column(Integer, ForeignKey("store.id"), nullable=False, index=True)
    bounced_on      = Column(Date, nullable=False)
    customer_name   = Column(String(120), nullable=False)
    # Company on the check / associated business. Required at the API
    # level (non-empty); the column carries a server_default so the
    # add-column migration backfills existing rows cleanly.
    company_name    = Column(String(120), nullable=False, server_default="")
    check_number    = Column(String(40),  default="")
    payer_bank      = Column(String(120), default="")
    # Integer cents (P0-3) — dollar views via the @property pairs
    # below (see Transfers/INVARIANTS.md for the pattern).
    amount_cents    = Column(BigInteger,  nullable=False, default=0)
    # Fee the store charges on a returned check (optional). Stored on
    # the record for reference; does not auto-feed the P&L — the daily
    # book's own return_check_hold_fees line stays the operator-entered
    # source for that.
    return_check_fee_cents = Column(BigInteger, nullable=False, server_default="0", default=0)
    status          = Column(String(16),  default="pending", nullable=False)
    status_changed_on = Column(Date,      nullable=True)
    notes           = Column(Text,        default="")
    created_by      = Column(Integer, ForeignKey("user.id"), nullable=True)
    created_at      = Column(DateTime, default=datetime.utcnow)
    updated_at      = Column(DateTime, default=datetime.utcnow,
                              onupdate=datetime.utcnow)

    payments = relationship(
        "ReturnCheckPayment",
        backref="return_check",
        cascade="all, delete-orphan",
        order_by="ReturnCheckPayment.paid_on, ReturnCheckPayment.id",
    )

    @property
    def amount(self) -> float:
        return to_dollars(self.amount_cents)  # type: ignore[arg-type]

    @amount.setter
    def amount(self, dollars: object) -> None:
        self.amount_cents = to_cents(dollars)  # type: ignore[assignment]

    @property
    def return_check_fee(self) -> float:
        return to_dollars(self.return_check_fee_cents)  # type: ignore[arg-type]

    @return_check_fee.setter
    def return_check_fee(self, dollars: object) -> None:
        self.return_check_fee_cents = to_cents(dollars)  # type: ignore[assignment]

    @property
    def recovered_total_cents(self) -> int:
        """Sum of all installment payments, in exact cents. Source
        of truth for 'how much have we got back so far'."""
        return int(sum((p.amount_cents or 0) for p in (self.payments or [])))

    @property
    def recovered_total(self) -> float:
        return to_dollars(self.recovered_total_cents)

    @property
    def total_due_cents(self) -> int:
        """Full balance the customer owes on this check, in exact
        cents: the face ``amount`` plus any ``return_check_fee`` the
        store charges for the bounce. This is the target the recovery
        workflow pays down to — a check isn't fully recovered until
        the fee is collected too, and collected fee dollars ride the
        payment→P&L recovery feed like the principal."""
        return int(self.amount_cents or 0) + int(self.return_check_fee_cents or 0)

    @property
    def total_due(self) -> float:
        return to_dollars(self.total_due_cents)

    @property
    def remaining_cents(self) -> int:
        """Outstanding cents against ``total_due_cents``. Never goes
        negative because the payment endpoint caps each installment
        at remaining."""
        return max(0, self.total_due_cents - self.recovered_total_cents)

    @property
    def remaining(self) -> float:
        return to_dollars(self.remaining_cents)

    @property
    def days_outstanding(self) -> int:
        """Calendar days since the check bounced. Used for aging
        buckets on the list and owner dashboard. Closed rows freeze
        at the days-to-close so the value is meaningful for fraud /
        write-off reporting too."""
        end = self.status_changed_on if self.status != "pending" else date.today()
        if not self.bounced_on or not end:
            return 0
        return int((end - self.bounced_on).days)


class ReturnCheckPayment(Base):
    """One installment of repayment against a ``ReturnCheck``.

    Splitting payments off into their own table is what lets the
    workflow handle the realistic case: a customer bounces a $1,000
    check, brings $300 in cash on April 15, $400 by Zelle on May 10,
    then the rest in June. Each row here represents one of those
    events, posts to its own day's daily book + P&L, and
    independently rolls up into the parent ``ReturnCheck``'s
    ``recovered_total``.

    Auto-creates a matching ``DailyLineItem(kind='return_payback')``
    on ``paid_on`` when inserted via the route handler — that's how
    the daily-book "Return Check Paid Back" line stays in sync
    without double-entry.
    """

    __tablename__ = "return_check_payment"
    id                 = Column(Integer, primary_key=True)
    return_check_id    = Column(Integer,
                                 ForeignKey("return_check.id"),
                                 nullable=False, index=True)
    amount_cents       = Column(BigInteger, nullable=False, default=0)
    paid_on            = Column(Date,  nullable=False)
    # cash / check / zelle / wire / money_order / other — see
    # ``_PAYMENT_METHODS`` for the canonical set. Free-form on save
    # so a future method can be added by widening the form's
    # ``<select>`` without a migration.
    payment_method     = Column(String(20), default="")
    note               = Column(String(200), default="")

    @property
    def amount(self) -> float:
        return to_dollars(self.amount_cents)  # type: ignore[arg-type]

    @amount.setter
    def amount(self, dollars: object) -> None:
        self.amount_cents = to_cents(dollars)  # type: ignore[assignment]
    created_by         = Column(Integer, ForeignKey("user.id"),
                                 nullable=True)
    created_at         = Column(DateTime, default=datetime.utcnow)


__all__ = [
    "RETURN_CHECK_BOOKED", "RETURN_CHECK_STATUSES",
    "ReturnCheck", "ReturnCheckPayment",
]
