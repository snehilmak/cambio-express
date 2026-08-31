"""StoreBook — Services.

The sheet's arithmetic and its write rules. Three column totals and
the variance between two of them; everything else on the page
exists to explain that variance.
"""
from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy.orm import Session

from api.Core.Clock import utc_now
from api.Modules.StoreBook.Models import (
    COUNT_FIELDS, FIELD_COLUMN, MONEY_FIELDS,
    StoreDailyEntry, StoreDailyEntryOriginal,
)


class StoreBookError(Exception):
    """User-safe failure (locked day, unknown field…)."""


class DayLockedError(StoreBookError):
    """The day is locked and the caller tried to write to it."""


def get_or_create_entry(
    db: Session, store_id: int, day: date,
) -> StoreDailyEntry:
    """The sheet for one day, created empty on first touch.

    Opening a day is not a mutation the operator has to think
    about — the row appears the moment anyone looks at it, exactly
    like the MSB book.
    """
    entry = (
        db.query(StoreDailyEntry)
        .filter_by(store_id=store_id, entry_date=day)
        .first()
    )
    if entry is None:
        entry = StoreDailyEntry(store_id=store_id, entry_date=day)
        db.add(entry)
        db.flush()
    return entry


def column_totals(entry: StoreDailyEntry) -> dict[str, int]:
    """The three running totals, in cents.

    Each column is the plain sum of its own fields. No field is
    counted twice and none is signed specially: an operator reading
    the page must be able to add the column up by hand and get the
    same number, or they will stop trusting it.
    """
    totals = {"sales": 0, "tenders": 0, "deposit": 0}
    for key in MONEY_FIELDS:
        totals[FIELD_COLUMN[key]] += int(
            getattr(entry, f"{key}_cents", 0) or 0,
        )
    return totals


def over_short_cents(entry: StoreDailyEntry) -> int:
    """Tenders minus sales — the number the whole sheet is for.

    Positive means more was accounted for than the register says
    was sold (an overage); negative is a shortage. It is a plain
    subtraction of the two column totals, so it always agrees with
    what the operator can add up on screen.
    """
    totals = column_totals(entry)
    return totals["tenders"] - totals["sales"]


def is_locked(entry: StoreDailyEntry) -> bool:
    return entry.locked_at is not None


def _assert_writable(entry: StoreDailyEntry) -> None:
    if is_locked(entry):
        raise DayLockedError(
            "This day is locked. Unlock it before making changes.",
        )


def update_entry(
    db: Session, entry: StoreDailyEntry, values: dict[str, Any],
) -> StoreDailyEntry:
    """Apply an operator edit. Money arrives in CENTS.

    Unknown keys are rejected rather than ignored: a typo in a
    field name would otherwise look like a successful save that
    silently dropped the number.
    """
    _assert_writable(entry)
    money = set(MONEY_FIELDS)
    counts = set(COUNT_FIELDS)
    for key, raw in values.items():
        if key in money:
            setattr(entry, f"{key}_cents", int(raw or 0))
        elif key in counts:
            # fuel_gallons is volume; the rest are integer counts.
            setattr(
                entry, key,
                float(raw or 0) if key.endswith("gallons") else int(raw or 0),
            )
        elif key == "notes":
            entry.notes = str(raw or "")[:2000]
        else:
            raise StoreBookError(f"Unknown field {key!r}.")
    entry.updated_at = utc_now()
    db.flush()
    return entry


def set_lock(
    db: Session, entry: StoreDailyEntry, *, locked: bool, user_id: int | None,
) -> StoreDailyEntry:
    """Lock or unlock the day. Idempotent."""
    if locked:
        if entry.locked_at is None:
            entry.locked_at = utc_now()
            entry.locked_by = user_id
    else:
        entry.locked_at = None
        entry.locked_by = None
    db.flush()
    return entry


def originals_for(entry: StoreDailyEntry) -> dict[str, int]:
    """``{field_key: cents}`` of what the POS reported, for the
    "Orig. Val" caption under each imported field."""
    return {
        row.field_key: int(row.amount_cents or 0)
        for row in entry.originals
    }


def apply_import(
    db: Session, entry: StoreDailyEntry, values: dict[str, int], *,
    source: str,
) -> StoreDailyEntry:
    """Write POS-derived values onto the sheet, recording each as
    the field's original.

    **A locked day still accepts imports.** The lock protects the
    operator's numbers from being edited, not the store's record
    from receiving what the register actually did — silently
    dropping a day's POS data because someone locked the sheet
    early would lose money data with no trace. The import lands,
    the original is recorded, and the operator sees their value and
    the register's side by side.

    Fields the operator has already overridden keep the operator's
    value; only the recorded original is refreshed. Deciding to
    take the register's number back is an explicit act (the refresh
    control on the field), never something an import does behind
    them.
    """
    known = set(MONEY_FIELDS)
    existing = {row.field_key: row for row in entry.originals}
    for key, cents in values.items():
        if key not in known:
            raise StoreBookError(f"Unknown field {key!r}.")
        cents = int(cents or 0)
        prior = existing.get(key)
        operator_edited = (
            prior is not None
            and int(getattr(entry, f"{key}_cents", 0) or 0)
            != int(prior.amount_cents or 0)
        )
        if prior is None:
            # Append through the relationship rather than db.add():
            # a bare add leaves `entry.originals` stale in this
            # session, so the very next read of the "Orig. Val"
            # captions would come back empty.
            entry.originals.append(StoreDailyEntryOriginal(
                store_id=entry.store_id,
                field_key=key, amount_cents=cents, source=source,
                imported_at=utc_now(),
            ))
        else:
            prior.amount_cents = cents
            prior.source = source
            prior.imported_at = utc_now()
        if not operator_edited:
            setattr(entry, f"{key}_cents", cents)
    entry.updated_at = utc_now()
    db.flush()
    return entry


def restore_original(
    db: Session, entry: StoreDailyEntry, field_key: str,
) -> StoreDailyEntry:
    """Take the register's number back for one field — the refresh
    control next to an overridden value."""
    _assert_writable(entry)
    if field_key not in set(MONEY_FIELDS):
        raise StoreBookError(f"Unknown field {field_key!r}.")
    original = next(
        (r for r in entry.originals if r.field_key == field_key), None,
    )
    if original is None:
        raise StoreBookError(
            "That field has no imported value to restore.",
        )
    setattr(entry, f"{field_key}_cents", int(original.amount_cents or 0))
    entry.updated_at = utc_now()
    db.flush()
    return entry


def month_summary(
    db: Session, store_id: int, year: int, month: int,
) -> list[dict[str, Any]]:
    """One row per day that has a sheet, for the month calendar:
    the day, its sales total, and whether it is locked."""
    from calendar import monthrange
    start = date(year, month, 1)
    end = date(year, month, monthrange(year, month)[1])
    rows = (
        db.query(StoreDailyEntry)
        .filter(
            StoreDailyEntry.store_id == store_id,
            StoreDailyEntry.entry_date >= start,
            StoreDailyEntry.entry_date <= end,
        )
        .order_by(StoreDailyEntry.entry_date.asc())
        .all()
    )
    out = []
    for entry in rows:
        totals = column_totals(entry)
        out.append({
            "entry_date": entry.entry_date.isoformat(),
            "sales_cents": totals["sales"],
            "tenders_cents": totals["tenders"],
            "deposit_cents": totals["deposit"],
            "over_short_cents": totals["tenders"] - totals["sales"],
            "is_locked": entry.locked_at is not None,
        })
    return out


__all__ = [
    "COUNT_FIELDS",
    "DayLockedError", "StoreBookError", "apply_import",
    "column_totals", "get_or_create_entry", "is_locked",
    "month_summary", "originals_for", "over_short_cents",
    "restore_original", "set_lock", "update_entry",
]
