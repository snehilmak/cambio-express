"""Fees vs. Federal Tax report aggregator.

Side-by-side: total fees (store revenue) vs. total federal tax
(passes through with the ACH withdrawal). Useful for sanity-
checking that the federal-tax rate is being applied
consistently — if the ratio drifts wildly between periods, a
config (or rate-rounding) bug is the likely culprit.

Pure DB read — no commits, no side-effects.
"""
from datetime import date

from sqlalchemy import func
from sqlalchemy.orm import Session


def fees_vs_tax(
    db: Session,
    store_ids: list[int],
    d_from: date,
    d_to: date,
) -> tuple[list[dict], dict]:
    """Total fees + federal tax in the window.

    Returns `(rows, totals)`:
      - rows: 2-element list with `label`, `amount`, `note` for
        the side-by-side display
      - totals: `fees`, `tax`, `count`, `ratio`
        (tax / fees, 0.0 when fees is 0).

    Empty `store_ids` → empty rows + zero totals (caller doesn't
    need to short-circuit).
    """
    from api.Modules.Transfers.Models import Transfer
    from api.Modules.Reports.Repositories.transfers import period_filters

    if not store_ids:
        return [], {"fees": 0.0, "tax": 0.0, "count": 0, "ratio": 0.0}

    fee_total, tax_total, count = (
        db.query(
            func.coalesce(func.sum(Transfer.fee), 0.0),
            func.coalesce(func.sum(Transfer.federal_tax), 0.0),
            func.count(Transfer.id),
        )
        .filter(*period_filters(store_ids, d_from, d_to))
        .one()
    )
    fee_total = float(fee_total or 0.0)
    tax_total = float(tax_total or 0.0)
    rows = [
        {
            "label":  "Fees (store revenue)",
            "amount": fee_total,
            "note":   "Stays with the store as transaction fee revenue.",
        },
        {
            "label":  "Federal Tax (pass-through)",
            "amount": tax_total,
            "note":   "Leaves with the ACH withdrawal — not store revenue.",
        },
    ]
    totals = {
        "fees":  fee_total,
        "tax":   tax_total,
        "count": int(count or 0),
        "ratio": (tax_total / fee_total) if fee_total else 0.0,
    }
    return rows, totals
