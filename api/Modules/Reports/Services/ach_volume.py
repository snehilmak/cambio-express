"""ACH volume report aggregator.

Groups `ACHBatch` rows in the period by company. Per-company:
batch count + total `ach_amount`. Used to surface which money-
transfer companies are driving the most ACH volume in the
selected window.

Pure DB read — no commits, no side-effects.
"""
from datetime import date

from sqlalchemy import func
from sqlalchemy.orm import Session
from typing import Any


def ach_volume(
    db: Session,
    store_ids: list[int],
    d_from: date,
    d_to: date,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Group ACHBatch rows in the window by company.

    Returns `(rows, totals)`:
      - rows: per-company dicts with `company`, `count`,
        `amount`, `avg`. Sorted descending by `amount` so the
        biggest mover lands first. Companies with NULL stored
        as `"(no company)"` for display.
      - totals: `count` (total batches), `amount` (total ACH).
    """
    from api.Modules.Batches.Models import ACHBatch

    rows_q = (
        db.query(
            ACHBatch.company,
            func.count(ACHBatch.id),
            func.coalesce(func.sum(ACHBatch.ach_amount), 0.0),
        )
        .filter(
            ACHBatch.store_id.in_(store_ids),
            ACHBatch.ach_date >= d_from,
            ACHBatch.ach_date <= d_to,
        )
        .group_by(ACHBatch.company)
        .all()
    )
    rows: list[dict[str, Any]] = []
    totals = {"count": 0, "amount": 0.0}
    for company, count, amount in rows_q:
        c = int(count or 0)
        a = float(amount or 0.0)
        rows.append({
            "company": company or "(no company)",
            "count":   c,
            "amount":  a,
            "avg":     (a / c) if c else 0.0,
        })
        totals["count"]  += c
        totals["amount"] += a
    rows.sort(key=lambda r: r["amount"], reverse=True)
    return rows, totals
