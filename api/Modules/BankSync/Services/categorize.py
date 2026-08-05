"""Bank-transaction category-assignment Service.

Two thin helpers extracted from the legacy
`_categorize_bank_transaction` / `_uncategorize_bank_transaction` in
app.py. They handle the BankTransaction.category_slug update +
optional DailyLineItem create/delete linkage, and crank the
BankRule.match_count counter when a rule auto-fired.

The legacy module-level state (`_is_daily_book_kind`) is passed in
as a callable so the Flask app keeps its existing helper while the
Service stays HTTP-agnostic.
"""
from datetime import date
from typing import Callable

from sqlalchemy.orm import Session

from api.Modules.BankSync.Models import BankRule, BankTransaction
from api.Modules.DailyBook.Models import DailyLineItem
from api.Core.Clock import utc_now


def categorize_transaction(
    db: Session, txn: BankTransaction, target_kind: str,
    *,
    rule: BankRule | None = None,
    post_to_daily: bool = True,
    report_date: date | None = None,
    is_daily_book_kind: Callable[[str], bool] | None = None,
) -> BankTransaction:
    """Set the transaction's category, optionally linking a daily-book
    line item. Idempotent — re-categorizing removes any previously
    auto-created DailyLineItem before adding a fresh one.

    `is_daily_book_kind` is a callable that returns True when the
    target_kind is a daily-book line-item kind (and therefore should
    create the DailyLineItem). Passed in so the legacy
    `_is_daily_book_kind` keeps living in app.py until the kind
    registry migrates too. None disables the daily-book post entirely.

    `report_date` overrides the line-item's report_date — used by the
    RDC case where the bank posts the transaction the next morning
    but the cash-handling event belongs on the previous day's book.
    """
    # Drop any prior auto-created DailyLineItem
    if txn.daily_line_item_id:
        old = db.get(DailyLineItem, txn.daily_line_item_id)
        if old is not None:
            db.delete(old)
        txn.daily_line_item_id = None

    txn.category_slug = target_kind or ""
    txn.matched_rule_id = rule.id if rule else None

    if rule is not None:
        rule.match_count = (rule.match_count or 0) + 1
        rule.last_matched_at = utc_now()

    if (
        post_to_daily and target_kind
        and is_daily_book_kind is not None
        and is_daily_book_kind(target_kind)
    ):
        when = txn.posted_at or utc_now()
        line_date = report_date if report_date is not None else when.date()
        line = DailyLineItem(
            store_id=txn.store_id,
            report_date=line_date,
            kind=target_kind,
            at_time=when.time(),
            # Daily-book stores absolute amounts; the kind encodes
            # inflow vs outflow on the report.
            amount=abs(float(txn.amount_cents or 0) / 100.0),
            note=(txn.description or "")[:120],
        )
        db.add(line)
        db.flush()
        txn.daily_line_item_id = line.id
    return txn


def uncategorize_transaction(
    db: Session, txn: BankTransaction,
) -> BankTransaction:
    """Clear category_slug + delete any auto-created DailyLineItem.
    Caller commits."""
    if txn.daily_line_item_id:
        old = db.get(DailyLineItem, txn.daily_line_item_id)
        if old is not None:
            db.delete(old)
        txn.daily_line_item_id = None
    txn.category_slug = ""
    txn.matched_rule_id = None
    return txn
