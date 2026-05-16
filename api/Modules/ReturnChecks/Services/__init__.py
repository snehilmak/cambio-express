"""ReturnChecks — Services."""
from datetime import date, datetime, time
from dataclasses import dataclass

from sqlalchemy import func
from sqlalchemy.orm import Session

from api.Modules.DailyBook.Models import DailyLineItem
from api.Modules.DailyBook.Services.line_items import (
    recompute_line_items_total,
)
from api.Modules.ReturnChecks.Models import (
    ReturnCheck, ReturnCheckPayment,
)
from api.Modules.ReturnChecks.Repositories import (
    find_payment, find_return_check,
)


class ReturnCheckNotFoundError(LookupError):
    pass


class ReturnCheckPaymentNotFoundError(LookupError):
    pass


class ReturnCheckStateError(ValueError):
    """Raised on illegal state transitions (e.g. marking a recovered
    row as loss without first reopening it)."""


@dataclass
class ReturnCheckWriteInput:
    bounced_on: date
    customer_name: str
    check_number: str
    payer_bank: str
    amount: float
    notes: str = ""


def create_return_check(
    db: Session, *, store_id: int, created_by: int | None,
    payload: ReturnCheckWriteInput,
) -> ReturnCheck:
    """Insert a new ReturnCheck row in pending status. Caller commits."""
    row = ReturnCheck(
        store_id=store_id,
        bounced_on=payload.bounced_on,
        customer_name=payload.customer_name,
        check_number=payload.check_number,
        payer_bank=payload.payer_bank,
        amount=float(payload.amount or 0),
        status="pending",
        notes=payload.notes,
        created_by=created_by,
    )
    db.add(row)
    db.flush()
    return row


def update_return_check(
    db: Session, *, store_id: int, rc_id: int,
    payload: ReturnCheckWriteInput,
) -> ReturnCheck:
    """Edit the core fields. Status / status_changed_on stay
    out of this path — those flow through the dedicated transition
    helpers below. Cross-tenant lookups raise NotFound."""
    row = find_return_check(db, store_id, rc_id)
    if row is None:
        raise ReturnCheckNotFoundError(f"id={rc_id}")
    row.bounced_on = payload.bounced_on
    row.customer_name = payload.customer_name
    row.check_number = payload.check_number
    row.payer_bank = payload.payer_bank
    row.amount = float(payload.amount or 0)
    row.notes = payload.notes
    db.flush()
    return row


def _set_status(
    db: Session, store_id: int, rc_id: int,
    *, target_status: str, allowed_from: tuple[str, ...],
) -> ReturnCheck:
    row = find_return_check(db, store_id, rc_id)
    if row is None:
        raise ReturnCheckNotFoundError(f"id={rc_id}")
    if row.status not in allowed_from:
        raise ReturnCheckStateError(
            f"Cannot move from {row.status} to {target_status}.",
        )
    row.status = target_status
    row.status_changed_on = date.today()
    row.updated_at = datetime.utcnow()
    db.flush()
    return row


def mark_loss(db: Session, store_id: int, rc_id: int) -> ReturnCheck:
    """Move pending → loss. The full `amount` becomes the loss in
    the month identified by `status_changed_on`."""
    return _set_status(
        db, store_id, rc_id,
        target_status="loss",
        allowed_from=("pending",),
    )


def mark_fraud(db: Session, store_id: int, rc_id: int) -> ReturnCheck:
    """Move pending → fraud. Same accounting as loss; tracked
    distinctly for fraud reporting."""
    return _set_status(
        db, store_id, rc_id,
        target_status="fraud",
        allowed_from=("pending",),
    )


def reopen(db: Session, store_id: int, rc_id: int) -> ReturnCheck:
    """Reopen a closed (loss / fraud / recovered) row back to
    pending. Clears status_changed_on so the row no longer
    contributes to any month's P&L until re-closed."""
    row = find_return_check(db, store_id, rc_id)
    if row is None:
        raise ReturnCheckNotFoundError(f"id={rc_id}")
    if row.status not in ("loss", "fraud", "recovered"):
        raise ReturnCheckStateError(
            f"Cannot reopen from status {row.status}.",
        )
    row.status = "pending"
    row.status_changed_on = None
    row.updated_at = datetime.utcnow()
    db.flush()
    return row


# ── Payments ────────────────────────────────────────────────────
#
# Each ``ReturnCheckPayment`` row mirrors one ``DailyLineItem
# (kind='return_payback')`` on its ``paid_on`` date. The shadow
# line item keeps the daily-book "Return Check Paid Back" total
# in sync without double-entry.
#
# We sync the line items via a recompute strategy rather than a
# 1:1 row reference: on every add/delete we wipe the line items
# linked to this return-check on the affected ``paid_on`` and
# re-insert from the surviving payments. That sidesteps the need
# for an FK column linking each payment to its specific line
# item, and survives bulk imports + manual SQL fixups.


@dataclass
class RecordPaymentInput:
    paid_on: date
    amount: float
    method: str = ""
    note: str = ""


# Default time-of-day stamped on the auto-generated DailyLineItem
# rows. The line items roll up into daily totals so the exact
# wall-clock doesn't matter — we just need a deterministic value
# so re-syncs are stable.
_DEFAULT_PAYBACK_TIME = time(9, 0)


def _resync_paybacks_for_day(
    db: Session, rc: ReturnCheck, report_date: date,
) -> None:
    """Wipe + re-create the DailyLineItem(kind='return_payback')
    rows for ``rc`` on ``report_date``, then re-derive the matching
    DailyReport total. Caller flushes / commits.
    """
    db.query(DailyLineItem).filter_by(
        return_check_id=rc.id,
        report_date=report_date,
        kind="return_payback",
    ).delete(synchronize_session=False)
    payments = (
        db.query(ReturnCheckPayment)
          .filter_by(return_check_id=rc.id, paid_on=report_date)
          .all()
    )
    note = f"Payback on {rc.customer_name}'s returned check"[:120]
    for p in payments:
        db.add(DailyLineItem(
            store_id=rc.store_id,
            report_date=p.paid_on,
            kind="return_payback",
            at_time=_DEFAULT_PAYBACK_TIME,
            amount=float(p.amount or 0.0),
            note=note,
            return_check_id=rc.id,
            created_by=p.created_by,
        ))
    db.flush()
    recompute_line_items_total(
        db, rc.store_id, report_date,
        kind="return_payback",
        daily_report_field="return_check_paid_back",
    )


def _maybe_auto_recover(
    db: Session, rc: ReturnCheck,
) -> None:
    """Auto-flip pending → recovered when payments meet the amount,
    or recovered → pending when a delete drops below it. Other
    closed statuses (loss / fraud) aren't touched — the cashier
    has to explicitly Reopen those before payments matter.

    Computes the running total via direct query rather than reading
    ``rc.recovered_total`` (the model property) because the parent
    ``rc.payments`` relationship doesn't auto-refresh after a flush
    that adds/removes a child row.
    """
    total = float(
        db.query(func.coalesce(func.sum(ReturnCheckPayment.amount), 0.0))
          .filter_by(return_check_id=rc.id)
          .scalar() or 0.0
    )
    full = float(rc.amount or 0.0)
    if rc.status == "pending" and total >= full and full > 0:
        rc.status = "recovered"
        rc.status_changed_on = date.today()
        rc.updated_at = datetime.utcnow()
    elif rc.status == "recovered" and total < full:
        rc.status = "pending"
        rc.status_changed_on = None
        rc.updated_at = datetime.utcnow()


def record_payment(
    db: Session, *, store_id: int, rc_id: int,
    created_by: int | None, payload: RecordPaymentInput,
) -> ReturnCheckPayment:
    """Insert a ReturnCheckPayment + the matching DailyLineItem,
    then re-derive the DailyReport total + parent status.

    Each installment is capped at ``rc.remaining`` so a cashier
    can't overpay; the legacy form enforced this at submit time
    and we match that. Caller commits the surrounding transaction.
    """
    rc = find_return_check(db, store_id, rc_id)
    if rc is None:
        raise ReturnCheckNotFoundError(f"id={rc_id}")
    if rc.status in ("loss", "fraud"):
        raise ReturnCheckStateError(
            f"Reopen the check before recording a payback "
            f"(current status: {rc.status}).",
        )
    amount = float(payload.amount or 0.0)
    if amount <= 0:
        raise ReturnCheckStateError("Payment amount must be > 0.")
    # Direct query so the cap accounts for payments added in the
    # same session that haven't yet been reloaded into the
    # ``rc.payments`` relationship.
    existing = float(
        db.query(func.coalesce(func.sum(ReturnCheckPayment.amount), 0.0))
          .filter_by(return_check_id=rc.id)
          .scalar() or 0.0
    )
    cap = max(0.0, float(rc.amount or 0.0) - existing)
    if cap <= 0:
        raise ReturnCheckStateError(
            "Return check is already fully recovered.",
        )
    amount = min(amount, cap)
    row = ReturnCheckPayment(
        return_check_id=rc.id,
        amount=amount,
        paid_on=payload.paid_on,
        payment_method=(payload.method or "").strip()[:20],
        note=(payload.note or "").strip()[:200],
        created_by=created_by,
    )
    db.add(row)
    db.flush()
    _resync_paybacks_for_day(db, rc, payload.paid_on)
    _maybe_auto_recover(db, rc)
    db.flush()
    return row


def delete_payment(
    db: Session, *, store_id: int, rc_id: int, payment_id: int,
) -> ReturnCheck:
    """Remove one installment + its matching DailyLineItem.

    If the parent was 'recovered' and the delete drops payments
    below the full amount, status reverts to 'pending'. Caller
    commits.
    """
    rc = find_return_check(db, store_id, rc_id)
    if rc is None:
        raise ReturnCheckNotFoundError(f"id={rc_id}")
    payment = find_payment(db, store_id, rc_id, payment_id)
    if payment is None:
        raise ReturnCheckPaymentNotFoundError(f"id={payment_id}")
    paid_on = payment.paid_on
    db.delete(payment)
    db.flush()
    _resync_paybacks_for_day(db, rc, paid_on)
    _maybe_auto_recover(db, rc)
    db.flush()
    return rc


__all__ = [
    "RecordPaymentInput",
    "ReturnCheckNotFoundError",
    "ReturnCheckPaymentNotFoundError",
    "ReturnCheckStateError",
    "ReturnCheckWriteInput",
    "create_return_check",
    "delete_payment",
    "mark_fraud",
    "mark_loss",
    "record_payment",
    "reopen",
    "update_return_check",
]
