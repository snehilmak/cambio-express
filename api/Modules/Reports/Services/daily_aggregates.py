"""Daily aggregate report services.

`DailyDrop` and `CheckDeposit` aggregate identically — group by
`report_date`, sum amount + count, sort newest-first, plus an
average-per-day total. Sharing a helper keeps the two services
behaviourally locked.

Pure DB read — no commits, no side-effects.
"""
from datetime import date

from sqlalchemy import func
from sqlalchemy.orm import Session


def _by_report_date(
    db: Session,
    model,
    store_ids: list[int],
    d_from: date,
    d_to: date,
) -> tuple[list[dict], dict]:
    """Group `model` rows by `report_date` and sum amount + count.
    `model` must expose `store_id`, `report_date`, `id`, `amount`."""
    rows_q = (
        db.query(
            model.report_date,
            func.count(model.id),
            func.coalesce(func.sum(model.amount), 0.0),
        )
        .filter(
            model.store_id.in_(store_ids),
            model.report_date >= d_from,
            model.report_date <= d_to,
        )
        .group_by(model.report_date)
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
) -> tuple[list[dict], dict]:
    """Aggregate `DailyDrop` rows in the period, grouped by date."""
    from app import DailyDrop
    return _by_report_date(db, DailyDrop, store_ids, d_from, d_to)


def check_deposits(
    db: Session,
    store_ids: list[int],
    d_from: date,
    d_to: date,
) -> tuple[list[dict], dict]:
    """Aggregate `CheckDeposit` rows in the period, grouped by date."""
    from app import CheckDeposit
    return _by_report_date(db, CheckDeposit, store_ids, d_from, d_to)
