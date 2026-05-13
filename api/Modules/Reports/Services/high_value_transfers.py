"""High-value transfers report aggregator.

Lists active transfers in the period whose `send_amount` is at
or above `threshold`. Unlike the other Reports services there
is no grouping — each row is a single transfer (the "headline
list" view used for compliance / KYC review). Sorted by
`send_amount` desc so the largest transactions surface first.

Pure DB read — no commits, no side-effects.
"""
from datetime import date

from sqlalchemy.orm import Session


def high_value_transfers(
    db: Session,
    store_ids: list[int],
    d_from: date,
    d_to: date,
    threshold: float,
) -> tuple[list[dict], dict]:
    """List active transfers ≥ `threshold` in the window.

    Returns `(rows, totals)`:
      - rows: per-transfer dicts with `send_date`, `sender_name`,
        `recipient_name`, `country`, `company`, `amount`, `fee`,
        `tax`, `confirm`. Sorted by amount desc, then send_date desc.
      - totals: `count`, `amount`, `fees`, `tax`.

    Uses `period_filters` so cancelled / refunded transfers are
    automatically excluded — same active-transfer definition as
    the other reports.
    """
    from api.Modules.Transfers.Models import Transfer
    from api.Modules.Reports.Repositories.transfers import period_filters

    rows_q = (
        db.query(Transfer)
          .filter(*period_filters(store_ids, d_from, d_to))
          .filter(Transfer.send_amount >= threshold)
          .order_by(
              Transfer.send_amount.desc(),
              Transfer.send_date.desc(),
          )
          .all()
    )
    rows = [
        {
            "send_date":      t.send_date,
            "sender_name":    t.sender_name or "",
            "recipient_name": t.recipient_name or "",
            "country":        t.country or "",
            "company":        t.company or "",
            "amount":         float(t.send_amount or 0),
            "fee":            float(t.fee or 0),
            "tax":            float(t.federal_tax or 0),
            "confirm":        t.confirm_number or "",
        }
        for t in rows_q
    ]
    totals = {
        "count":  len(rows),
        "amount": sum(r["amount"] for r in rows),
        "fees":   sum(r["fee"]    for r in rows),
        "tax":    sum(r["tax"]    for r in rows),
    }
    return rows, totals
