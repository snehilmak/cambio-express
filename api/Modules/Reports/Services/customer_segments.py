"""New-vs-returning customer segmentation aggregator.

Splits senders active in the period into "new" vs "returning"
based on whether they had any prior transfer with the store(s)
before `d_from`. Walk-in transfers (customer_id IS NULL) can't
be classified — same person can't be tracked across visits —
so they're aggregated as a third bucket.

Pure DB read — no commits, no side-effects.
"""
from datetime import date

from sqlalchemy import func
from sqlalchemy.orm import Session


def new_vs_returning(
    db: Session,
    store_ids: list[int],
    d_from: date,
    d_to: date,
) -> tuple[list[dict], dict]:
    """Aggregate senders into new / returning / walk-in buckets.

    Returns `(rows, totals)`:
      - rows: per-bucket dicts with `bucket`, `customers`, `txns`,
        `sent`, `tone`. The walk-in row is only emitted when there
        ARE walk-in transfers — empty buckets stay hidden so the
        template doesn't render a noisy zero row.
      - totals: cross-bucket sums + `new_count` / `returning_count`
        for the headline KPI.
    """
    from api.Modules.Transfers.Models import Transfer
    from api.Modules.Owners.Services import OWNER_TRANSFER_EXCLUDED
    from api.Modules.Reports.Repositories.transfers import period_filters

    period_q = (
        db.query(
            Transfer.customer_id,
            func.count(Transfer.id),
            func.coalesce(func.sum(Transfer.send_amount), 0.0),
        )
        .filter(*period_filters(store_ids, d_from, d_to))
        .group_by(Transfer.customer_id)
        .all()
    )

    new_count = returning_count = walkin_count = 0
    new_sent = returning_sent = walkin_sent = 0.0
    new_txns = returning_txns = walkin_txns = 0

    cust_ids = [c for c, _, _ in period_q if c is not None]
    pre_ids: set[int] = set()
    if cust_ids:
        pre_ids = {
            row[0]
            for row in (
                db.query(Transfer.customer_id)
                  .filter(
                      Transfer.store_id.in_(store_ids),
                      Transfer.send_date < d_from,
                      Transfer.status.notin_(OWNER_TRANSFER_EXCLUDED),
                      Transfer.customer_id.in_(cust_ids),
                  )
                  .distinct()
                  .all()
            )
        }

    for cid, count, sent in period_q:
        sent = float(sent or 0)
        count = int(count or 0)
        if cid is None:
            walkin_count += 1
            walkin_sent  += sent
            walkin_txns  += count
        elif cid in pre_ids:
            returning_count += 1
            returning_sent  += sent
            returning_txns  += count
        else:
            new_count += 1
            new_sent  += sent
            new_txns  += count

    rows: list[dict] = [
        {"bucket": "New senders",       "customers": new_count,
         "txns":   new_txns,            "sent":      new_sent,
         "tone":   "primary"},
        {"bucket": "Returning senders", "customers": returning_count,
         "txns":   returning_txns,      "sent":      returning_sent,
         "tone":   "neon"},
    ]
    if walkin_count:
        rows.append({
            "bucket": "Walk-in (unidentified)",
            "customers": walkin_count,
            "txns": walkin_txns,
            "sent": walkin_sent,
            "tone": "muted",
        })
    totals = {
        "customers": new_count + returning_count + walkin_count,
        "txns":      new_txns + returning_txns + walkin_txns,
        "sent":      new_sent + returning_sent + walkin_sent,
        "new_count":       new_count,
        "returning_count": returning_count,
    }
    return rows, totals
