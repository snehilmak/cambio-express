"""Daily aggregate report services.

Drops and check deposits aggregate identically — group by
`report_date`, sum amount + count, sort newest-first, plus an
average-per-day total. Sharing a helper keeps the two services
behaviourally locked.

Both read `DailyLineItem` by kind — the ONLY write path since the
legacy `DailyDrop` / `CheckDeposit` tables were retired (DailyBook
INVARIANTS "Data model"). History is covered too:
`Bootstrap.migrate_legacy_line_item_tables()` copied every legacy
row into `daily_line_item` at boot, so querying the line items
alone is complete — and UNIONing the legacy tables back in would
double-count all pre-conversion rows.

Pure DB read — no commits, no side-effects.
"""
from datetime import date

from sqlalchemy import func
from sqlalchemy.orm import Session
from typing import Any


def _line_items_by_report_date(
    db: Session,
    kind: str,
    store_ids: list[int],
    d_from: date,
    d_to: date,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Group `DailyLineItem` rows of one `kind` by `report_date` and
    sum amount + count."""
    from api.Modules.DailyBook.Models import DailyLineItem

    rows_q = (
        db.query(
            DailyLineItem.report_date,
            func.count(DailyLineItem.id),
            func.coalesce(func.sum(DailyLineItem.amount), 0.0),
        )
        .filter(
            DailyLineItem.store_id.in_(store_ids),
            DailyLineItem.kind == kind,
            DailyLineItem.report_date >= d_from,
            DailyLineItem.report_date <= d_to,
        )
        .group_by(DailyLineItem.report_date)
        .all()
    )
    rows = [
        {
            "date":   d,
            "count":  int(count or 0),
            "amount": float(amount or 0),
        }
        for d, count, amount in rows_q
    ]
    rows.sort(key=lambda r: r["date"], reverse=True)
    totals = {
        "count":  sum(r["count"]  for r in rows),
        "amount": sum(r["amount"] for r in rows),
    }
    totals["avg_per_day"] = (
        totals["amount"] / len(rows) if rows else 0.0
    )
    return rows, totals


def daily_drops(
    db: Session,
    store_ids: list[int],
    d_from: date,
    d_to: date,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Aggregate drop line items (`kind='drop'`) in the period,
    grouped by date."""
    return _line_items_by_report_date(db, "drop", store_ids, d_from, d_to)


def check_deposits(
    db: Session,
    store_ids: list[int],
    d_from: date,
    d_to: date,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Aggregate check-deposit line items (`kind='check_deposit'`)
    in the period, grouped by date."""
    return _line_items_by_report_date(
        db, "check_deposit", store_ids, d_from, d_to,
    )
