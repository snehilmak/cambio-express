"""Transfer-aggregation queries used by every Sales / Top-X report.

Two functions:

  period_filters(store_ids, d_from, d_to)
      Returns the standard `(store_id IN …, send_date BETWEEN …,
      status NOT IN canceled/rejected)` filter clauses, ready to
      spread into a SQLAlchemy `.filter(*…)` call.

  aggregate(db, store_ids, d_from, d_to, group_col)
      Groups active transfers by `group_col` and returns
      `(rows, totals)`. Each row exposes the grouped key + count
      + sums of send_amount / fee / federal_tax + a per-row avg.
      Totals carry the same sums across all rows.

Rows are NOT sorted here — Services own the sort order so report-
specific decisions (sort by sent desc, by count desc, alphabetical,
etc.) live one layer up.
"""
from datetime import date
from typing import Any, Iterable

from sqlalchemy.orm import Session
from sqlalchemy import func

from api.Modules.Reports.Models import Transfer, _OWNER_TRANSFER_EXCLUDED


def period_filters(
    store_ids: Iterable[int], d_from: date, d_to: date,
) -> tuple[Any, ...]:
    """Standard filter set every Transfer-based report uses: scoped
    to `store_ids` (list — accepts admin's `[single_id]` or owner's
    umbrella), posted in the period, and excluding Canceled / Rejected
    (same convention as the dashboard + owner pages).

    Spread into a `.filter(...)` call:

        q.filter(*period_filters(store_ids, d_from, d_to))
    """
    return (
        Transfer.store_id.in_(list(store_ids)),
        Transfer.send_date >= d_from,
        Transfer.send_date <= d_to,
        Transfer.status.notin_(_OWNER_TRANSFER_EXCLUDED),
    )


def aggregate(
    db: Session,
    store_ids: Iterable[int],
    d_from: date,
    d_to: date,
    group_col: Any,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Group active transfers in the period by `group_col`.

    Returns `(rows, totals)`:

      rows:  list[Any] of dicts with keys `key`, `count`, `sent`,
             `fees`, `tax`, `avg`. Unsorted — caller decides.
      totals: dict[str, Any] with `sent`, `fees`, `tax`, `count` summed
             across every row.

    Single GROUP BY query — O(distinct keys) memory, never loads
    individual transfer rows into Python.
    """
    rows_q = (
        db.query(
            group_col,
            func.count(Transfer.id),
            func.coalesce(func.sum(Transfer.send_amount), 0.0),
            func.coalesce(func.sum(Transfer.fee), 0.0),
            func.coalesce(func.sum(Transfer.federal_tax), 0.0),
        )
        .filter(*period_filters(store_ids, d_from, d_to))
        .group_by(group_col)
        .all()
    )

    rows: list[dict[str, Any]] = []
    totals = {"sent": 0.0, "fees": 0.0, "tax": 0.0, "count": 0}
    for key, count, sent, fees, tax in rows_q:
        c = int(count or 0)
        sent_f = float(sent or 0)
        fees_f = float(fees or 0)
        tax_f = float(tax or 0)
        rows.append(
            {
                "key": key,
                "count": c,
                "sent": sent_f,
                "fees": fees_f,
                "tax": tax_f,
                "avg": (sent_f / c) if c else 0.0,
            }
        )
        totals["sent"] += sent_f
        totals["fees"] += fees_f
        totals["tax"] += tax_f
        totals["count"] += c
    return rows, totals
