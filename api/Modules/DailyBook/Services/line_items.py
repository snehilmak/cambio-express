"""DailyLineItem write-side Service.

Add + delete operations for DailyLineItem rows + the
recompute-total helper that pushes the kind sum back onto the
DailyReport row's matching field. Validation lives here so a
malformed time/amount fails the same way regardless of whether the
request came in via Flask form-post or the future FastAPI
controller.
"""
from datetime import date, datetime, time
from typing import Iterable

from sqlalchemy import func
from sqlalchemy.orm import Session

from api.Modules.DailyBook.Models import DailyLineItem
from api.Modules.DailyBook.Services.reports import ensure_daily_report
from api.Core.Clock import utc_now


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
    kind: str, at_time: time | None, amount: float,
    note: str = "", created_by: int | None = None,
    allowed_kinds: Iterable[str] | None = None,
) -> DailyLineItem:
    """Insert one DailyLineItem. Caller is responsible for committing
    the surrounding transaction (and for re-deriving the
    DailyReport's discriminated total from these rows after the
    insert).

    ``allowed_kinds`` is an optional whitelist — passing it makes
    the Service reject unknown kinds before the INSERT lands.
    Empty / None skips the check and trusts the caller.
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


def update_line_item(
    db: Session, line_item: DailyLineItem,
    *,
    at_time: time | None = None,
    amount: float | None = None,
    note: str | None = None,
    allow_return_check_linked: bool = False,
) -> DailyLineItem:
    """Patch one DailyLineItem in place.  Caller fetches +
    scope-checks the row.  Only the fields whose argument was
    passed (not None) get written — partial PATCH semantics.

    Rejects updates on rows linked to a `ReturnCheck` (mirror of
    ReturnChecks-side state — daily-book edits can't drift those
    numbers).  Same guard as ``delete_line_item``.

    Caller commits the surrounding transaction and re-derives the
    DailyReport total via ``recompute_line_items_total`` after the
    update.
    """
    if (
        not allow_return_check_linked
        and line_item.return_check_id is not None
    ):
        raise LineItemValidationError(
            "This payback is linked to a return check. Edit it "
            "from Books → Return Checks (update the payment).",
        )
    if amount is not None:
        if amount <= 0:
            raise LineItemValidationError(
                "Amount must be greater than zero.",
            )
        # `setattr` rather than direct assignment — SQLAlchemy 1.x
        # column descriptors expose `Column[float]` to mypy, which
        # rejects `float` assignments under --strict.  Same trick
        # `recompute_line_items_total` uses below.
        setattr(line_item, "amount", float(amount))
    if at_time is not None:
        setattr(line_item, "at_time", at_time)
    if note is not None:
        setattr(line_item, "note", note.strip()[:120])
    db.flush()
    return line_item


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


def recompute_line_items_total(
    db: Session, store_id: int, report_date: date,
    *, kind: str, daily_report_field: str,
) -> float:
    """Sum DailyLineItem rows of the given kind for (store, date) and
    push the total onto the matching DailyReport field.

    `daily_report_field` is the attribute name on DailyReport that
    stores the rolled-up total for `kind` (e.g. `cash_purchase` →
    `cash_purchases`). The legacy `_LINE_ITEM_KINDS` map in app.py
    holds the kind→field mapping; the Service takes the field name
    explicitly so it doesn't have to know about the registry yet.

    Caller commits. Returns the total (useful for log output / test
    assertions).
    """
    total = (
        db.query(func.coalesce(func.sum(DailyLineItem.amount), 0.0))
          .filter_by(
              store_id=store_id,
              report_date=report_date,
              kind=kind,
          )
          .scalar()
    ) or 0.0
    report = ensure_daily_report(db, store_id, report_date)
    setattr(report, daily_report_field, float(total))
    setattr(report, "updated_at", utc_now())
    db.flush()
    return float(total)
