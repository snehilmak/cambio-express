"""Returned-check status report aggregator.

Groups `ReturnCheck` rows that bounced in the period by status.
Each bucket exposes count + total amount + total recovered_amount
(only meaningful for status='recovered'). Plus a derived net G/L
line: `recovered - (loss + fraud)`.

Pure DB read — no commits, no side-effects.
"""
from datetime import date

from sqlalchemy.orm import Session


def returned_check_status(
    db: Session,
    store_ids: list[int],
    d_from: date,
    d_to: date,
) -> tuple[list[dict], dict]:
    """Aggregate ReturnCheck rows by status with display-ready
    rows + cross-bucket totals.

    Returns `(rows, totals)`:
      - rows: per-status dicts with `status` (title-cased label),
        `status_key`, `count`, `amount`, `recovered`. Empty
        buckets are skipped so the template doesn't render
        zero-value cards.
      - totals: `count`, `amount`, `recovered`, `loss_fraud`,
        `net_gl` (recovered - loss_fraud).
    """
    from app import RETURN_CHECK_STATUSES, ReturnCheck

    rows_q = (
        db.query(ReturnCheck)
          .filter(
              ReturnCheck.store_id.in_(store_ids),
              ReturnCheck.bounced_on >= d_from,
              ReturnCheck.bounced_on <= d_to,
          )
          .all()
    )
    buckets: dict[str, dict] = {
        s: {"count": 0, "amount": 0.0, "recovered": 0.0}
        for s in RETURN_CHECK_STATUSES
    }
    for rc in rows_q:
        b = buckets.setdefault(
            rc.status,
            {"count": 0, "amount": 0.0, "recovered": 0.0},
        )
        b["count"]  += 1
        b["amount"] += float(rc.amount or 0)
        if rc.status == "recovered":
            b["recovered"] += float(rc.recovered_total or 0)

    display_order = ["pending", "recovered", "loss", "fraud"]
    rows: list[dict] = []
    for status in display_order:
        b = buckets.get(
            status, {"count": 0, "amount": 0.0, "recovered": 0.0},
        )
        if b["count"] == 0:
            continue
        rows.append({
            "status":     status.title(),
            "status_key": status,
            "count":      b["count"],
            "amount":     b["amount"],
            "recovered":  b["recovered"],
        })
    totals = {
        "count":      sum(b["count"]  for b in buckets.values()),
        "amount":     sum(b["amount"] for b in buckets.values()),
        "recovered":  buckets.get("recovered", {}).get("recovered", 0.0),
        "loss_fraud": (
            buckets.get("loss",  {}).get("amount", 0.0)
            + buckets.get("fraud", {}).get("amount", 0.0)
        ),
    }
    totals["net_gl"] = totals["recovered"] - totals["loss_fraud"]
    return rows, totals
