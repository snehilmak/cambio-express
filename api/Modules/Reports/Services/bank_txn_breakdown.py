"""Bank-transaction breakdown report aggregator.

Groups `BankTransaction` rows posted in the period by
`category_slug`, summing absolute amount + count. Uncategorised
rows bucketed under `""` (rendered as the operator-friendly
"(uncategorised)" label by `bank_category_label`). Inflow vs
outflow tracked separately so the template can show net cash
flow alongside gross volume.

Pure DB read — no commits, no side-effects.
"""
from datetime import date

from sqlalchemy import func
from sqlalchemy.orm import Session
from typing import Any


def bank_txn_breakdown(
    db: Session,
    store_ids: list[int],
    d_from: date,
    d_to: date,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Aggregate BankTransaction rows by category_slug.

    Returns `(rows, totals)`:
      - rows: per-category dicts with `slug`, `label`, `count`,
        `signed` (signed dollars), `amount` (absolute dollars).
        Sorted descending by absolute amount.
      - totals: `count`, `amount` (gross |amount|), `inflow`
        (positive dollars), `outflow` (negative dollars).
    """
    from api.Modules.BankSync.Models import BankTransaction
    from api.Modules.BankSync.Services import bank_category_label
    from api.Modules.Reports.Services.date_helpers import (
        day_end, day_start,
    )

    month_start = day_start(d_from)
    month_end   = day_end(d_to)
    rows_q = (
        db.query(
            BankTransaction.category_slug,
            func.count(BankTransaction.id),
            func.coalesce(func.sum(BankTransaction.amount_cents), 0),
        )
        .filter(
            BankTransaction.store_id.in_(store_ids),
            BankTransaction.posted_at >= month_start,
            BankTransaction.posted_at <= month_end,
        )
        .group_by(BankTransaction.category_slug)
        .all()
    )
    rows: list[dict[str, Any]] = []
    totals = {"count": 0, "amount": 0.0, "inflow": 0.0, "outflow": 0.0}
    for slug, count, cents in rows_q:
        c = int(count or 0)
        signed = float(cents or 0) / 100.0
        rows.append({
            "slug":   slug or "",
            "label":  bank_category_label(slug or ""),
            "count":  c,
            "signed": signed,
            "amount": abs(signed),
        })
        totals["count"]  += c
        totals["amount"] += abs(signed)
        if signed >= 0:
            totals["inflow"]  += signed
        else:
            totals["outflow"] += signed
    rows.sort(key=lambda r: r["amount"], reverse=True)
    return rows, totals
