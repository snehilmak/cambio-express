"""Returned-check status report aggregator.

Groups `ReturnCheck` rows that bounced in the period by status.
Each bucket exposes count + total amount + total recovered — the
sum of installment payments received so far, for EVERY status:
a still-pending check with money already paid back (principal
and/or the bounce fee) must show those dollars, not $0. Plus a
derived net G/L line: `recovered - (loss + fraud)`.

Pure DB read — no commits, no side-effects.
"""
from datetime import date

from sqlalchemy.orm import Session
from typing import Any


def returned_check_status(
    db: Session,
    store_ids: list[int],
    d_from: date,
    d_to: date,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
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
    from api.Modules.ReturnChecks.Models import RETURN_CHECK_STATUSES, ReturnCheck

    rows_q = (
        db.query(ReturnCheck)
          .filter(
              ReturnCheck.store_id.in_(store_ids),
              ReturnCheck.bounced_on >= d_from,
              ReturnCheck.bounced_on <= d_to,
          )
          .all()
    )
    buckets: dict[str, dict[str, Any]] = {
        s: {"count": 0, "amount": 0.0, "recovered": 0.0}
        for s in RETURN_CHECK_STATUSES
    }
    loss_fraud_net = 0.0
    for rc in rows_q:
        b = buckets.setdefault(
            str(rc.status),
            {"count": 0, "amount": 0.0, "recovered": 0.0},
        )
        b["count"]  += 1
        b["amount"] += float(rc.amount or 0)
        # recovered_total sums the installment payments (which pay
        # down face amount + the bounce fee) — real money back,
        # whatever the status. Gating this on status='recovered'
        # hid partial and even full paybacks on pending rows.
        recovered = float(rc.recovered_total or 0)
        b["recovered"] += recovered
        if rc.status in ("loss", "fraud"):
            # Net the write-off of anything already paid back —
            # counting the full face amount would double-count the
            # partial recovery (once in `recovered`, once here).
            # Mirrors Owners/Services/return_checks.writeoff_total.
            loss_fraud_net += max(0.0, float(rc.amount or 0) - recovered)

    display_order = ["pending", "recovered", "loss", "fraud"]
    rows: list[dict[str, Any]] = []
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
        "recovered":  sum(b["recovered"] for b in buckets.values()),
        # Net of partial recoveries (see loop above). NB: this report
        # is a BOUNCE-COHORT view — it windows on bounced_on, so its
        # net G/L can differ from the monthly P&L's Return Check
        # (G/L) line, which books recoveries by paid_on and losses by
        # status_changed_on.
        "loss_fraud": loss_fraud_net,
    }
    totals["net_gl"] = totals["recovered"] - totals["loss_fraud"]
    return rows, totals
