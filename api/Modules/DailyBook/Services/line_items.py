"""DailyLineItem write-side Service.

Add + delete operations for DailyLineItem rows. Validation lives
here so a malformed time/amount fails the same way regardless of
whether the request came in via Flask form-post or the future
FastAPI controller. The legacy `_recompute_line_items_total` and
the `return_payback` / `return_check_id` UX gates stay in app.py
for now — they touch the DailyReport rolled-up totals + the Return
Checks integration which haven't migrated yet.
"""
from datetime import date, datetime, time
from typing import Iterable

from sqlalchemy.orm import Session

from api.Modules.DailyBook.Models import DailyLineItem


class LineItemValidationError(ValueError):
    """User-facing validation failure. The message is safe to render
    to the cashier (matches the legacy form's flash strings)."""


def parse_at_time(raw: str) -> time:
    """Coerce a HH:MM form field into a datetime.time. Raises
    LineItemValidationError with the legacy "Enter a valid time
    (HH:MM)." message on parse failure."""
    try:
        return datetime.strptime(raw, "%H:%M").time()
    except (ValueError, TypeError):
        raise LineItemValidationError("Enter a valid time (HH:MM).")


def parse_amount(raw: str) -> float:
    """Coerce a form-field amount string to a positive float. Raises
    LineItemValidationError with the legacy "Amount must be greater
    than zero." message on parse failure or non-positive value."""
    try:
        amt = float(raw)
        if amt <= 0:
            raise ValueError
        return amt
    except (ValueError, TypeError):
        raise LineItemValidationError("Amount must be greater than zero.")


def add_line_item(
    db: Session, *, store_id: int, report_date: date,
    kind: str, at_time: time, amount: float,
    note: str = "", created_by: int | None = None,
    allowed_kinds: Iterable[str] | None = None,
) -> DailyLineItem:
    """Insert one DailyLineItem. Caller is responsible for committing
    the surrounding transaction (and for re-deriving the
    DailyReport's discriminated total from these rows after the
    insert).

    `allowed_kinds` is an optional whitelist — passing it makes the
    Service reject unknown kinds before the INSERT lands. Empty /
    None skips the check and trusts the caller (legacy Flask path
    uses `_line_item_kind_or_404` upstream for that).
    """
    if allowed_kinds is not None and kind not in allowed_kinds:
        raise LineItemValidationError(f"Unknown line-item kind: {kind!r}")
    row = DailyLineItem(
        store_id=store_id,
        report_date=report_date,
        kind=kind,
        at_time=at_time,
        amount=amount,
        note=(note or "").strip()[:120],
        created_by=created_by,
    )
    db.add(row)
    db.flush()
    return row


def delete_line_item(
    db: Session, line_item: DailyLineItem,
    *, allow_return_check_linked: bool = False,
) -> None:
    """Delete one DailyLineItem. Caller fetches + scope-checks the row.

    `allow_return_check_linked=False` is the default so the manual
    delete path can't strip a payback that was created by the Return
    Checks page (the daily book stays in sync with that source of
    truth). Pass True from the Return-Checks-side delete to allow it.
    """
    if (
        not allow_return_check_linked
        and line_item.return_check_id is not None
    ):
        raise LineItemValidationError(
            "This payback is linked to a return check. Remove it "
            "from Books → Return Checks (delete the payment).",
        )
    db.delete(line_item)
    db.flush()
