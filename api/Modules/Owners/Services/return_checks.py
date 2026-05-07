"""Owner-facing return-check rollups.

Five read-side aggregates the owner dashboard + monthly P&L share:

  - `writeoff_total(...)`  : sum unrecovered balance of closed
                              checks (loss / fraud) in a window.
  - `period_aggregates(...)`: recoveries (by payment date) +
                              losses + fraud + still-pending
                              balance for a window. Used by KPI
                              cards.
  - `aging_buckets(db, store_ids)`: pending balance sliced into
                              0–30 / 31–60 / 61–90 / 90+ buckets.
  - `monthly_series(db, store_ids)`: 12-month recoveries vs
                              losses-plus-fraud bars.
  - `monthly_pl(db, store_id, year, month)`: signed value for the
                              monthly P&L's Return Check (G/L)
                              line. Sign-flipped relative to
                              `period_aggregates['net_gl']` so
                              loss-positive (expense convention).

Per CLAUDE.md, recoveries are measured at the PAYMENT level (a
$300 installment in April + $400 in May → split across months);
losses/fraud are measured at the parent level on
`status_changed_on` (single closing event), summed against the
REMAINING balance (parent.amount − payments already received) so
partial recoveries before write-off don't double-count.
"""
from calendar import monthrange
from datetime import date

from sqlalchemy import func
from sqlalchemy.orm import Session


def _models():
    """Lazy-import the ORM models so this module can be imported
    before app.py finishes wiring up the model registry."""
    from app import ReturnCheck, ReturnCheckPayment
    return ReturnCheck, ReturnCheckPayment


def writeoff_total(
    db: Session,
    store_ids: list[int],
    start: date,
    end: date,
    status_value: str,
) -> float:
    """Sum the still-owed balance of return checks marked
    `status_value` (typically 'loss' or 'fraud') whose
    `status_changed_on` falls in `[start, end]`.

    Subtracts payments already received against each parent —
    partial recoveries before the close were already booked as
    recoveries in their own months.
    """
    if not store_ids:
        return 0.0
    ReturnCheck, ReturnCheckPayment = _models()
    rows = (
        db.query(ReturnCheck.id, ReturnCheck.amount)
          .filter(
              ReturnCheck.store_id.in_(store_ids),
              ReturnCheck.status == status_value,
              ReturnCheck.status_changed_on >= start,
              ReturnCheck.status_changed_on <= end,
          )
          .all()
    )
    if not rows:
        return 0.0
    rc_ids = [rid for rid, _ in rows]
    # Sum payments per parent in one query — avoids N+1.
    paid_rows = (
        db.query(
            ReturnCheckPayment.return_check_id,
            func.coalesce(func.sum(ReturnCheckPayment.amount), 0.0),
        )
        .filter(ReturnCheckPayment.return_check_id.in_(rc_ids))
        .group_by(ReturnCheckPayment.return_check_id)
        .all()
    )
    paid_by = {rid: float(s or 0.0) for rid, s in paid_rows}
    total = 0.0
    for rid, amt in rows:
        total += max(0.0, float(amt or 0.0) - paid_by.get(rid, 0.0))
    return total


def period_aggregates(
    db: Session, store_ids: list[int], start: date, end: date,
) -> dict:
    """Sum recoveries (by payment date) and losses+fraud (by parent
    status-change date), plus the still-pending balance.

    Returns gain-positive `net_gl` (used by the owner dashboard);
    `monthly_pl` flips the sign for the P&L expense column.

    Empty `store_ids` returns all-zero dict — caller doesn't need
    to short-circuit.
    """
    if not store_ids:
        return {
            "recoveries": 0.0, "losses": 0.0, "fraud": 0.0,
            "net_gl": 0.0, "pending": 0.0, "pending_count": 0,
        }
    ReturnCheck, ReturnCheckPayment = _models()

    # Recoveries: Σ payments by paid_on, joined to parent for the
    # store filter. Payment doesn't carry store_id — parent does
    # — so we join through.
    rec = (
        db.query(func.coalesce(func.sum(ReturnCheckPayment.amount), 0.0))
          .join(
              ReturnCheck,
              ReturnCheckPayment.return_check_id == ReturnCheck.id,
          )
          .filter(
              ReturnCheck.store_id.in_(store_ids),
              ReturnCheckPayment.paid_on >= start,
              ReturnCheckPayment.paid_on <= end,
          )
          .scalar() or 0.0
    )

    loss = writeoff_total(db, store_ids, start, end, "loss")
    fraud = writeoff_total(db, store_ids, start, end, "fraud")

    pending_q = (
        db.query(
            func.coalesce(func.sum(ReturnCheck.amount), 0.0),
            func.count(ReturnCheck.id),
        )
        .filter(
            ReturnCheck.store_id.in_(store_ids),
            ReturnCheck.status == "pending",
            ReturnCheck.bounced_on <= end,
        )
        .first()
    )
    pending_amount_total = float(pending_q[0] or 0.0)
    pending_count = int(pending_q[1] or 0)
    # Subtract installments already received against pending
    # parents so the "Pending balance" KPI shows OUTSTANDING owed,
    # not original face value.
    if pending_count > 0:
        pending_paid = (
            db.query(func.coalesce(func.sum(ReturnCheckPayment.amount), 0.0))
              .join(
                  ReturnCheck,
                  ReturnCheckPayment.return_check_id == ReturnCheck.id,
              )
              .filter(
                  ReturnCheck.store_id.in_(store_ids),
                  ReturnCheck.status == "pending",
                  ReturnCheck.bounced_on <= end,
              )
              .scalar() or 0.0
        )
        pending = max(0.0, pending_amount_total - float(pending_paid))
    else:
        pending = 0.0

    return {
        "recoveries":   float(rec),
        "losses":       float(loss),
        "fraud":        float(fraud),
        "net_gl":       float(rec) - float(loss) - float(fraud),
        "pending":      pending,
        "pending_count": pending_count,
    }


def aging_buckets(
    db: Session, store_ids: list[int], today: date | None = None,
) -> list[dict]:
    """Pending balance sliced into 0–30 / 31–60 / 61–90 / 90+
    buckets by `bounced_on`. Helps the owner spot stale
    receivables that probably won't recover."""
    if today is None:
        today = date.today()
    if not store_ids:
        return [
            {"label": "0–30 d",  "amount": 0.0, "count": 0},
            {"label": "31–60 d", "amount": 0.0, "count": 0},
            {"label": "61–90 d", "amount": 0.0, "count": 0},
            {"label": "90+ d",   "amount": 0.0, "count": 0},
        ]
    ReturnCheck, _ = _models()
    rows = (
        db.query(ReturnCheck)
          .filter(
              ReturnCheck.store_id.in_(store_ids),
              ReturnCheck.status == "pending",
          )
          .all()
    )
    buckets = [
        {"label": "0–30 d",  "amount": 0.0, "count": 0, "max": 30},
        {"label": "31–60 d", "amount": 0.0, "count": 0, "max": 60},
        {"label": "61–90 d", "amount": 0.0, "count": 0, "max": 90},
        {"label": "90+ d",   "amount": 0.0, "count": 0, "max": None},
    ]
    for r in rows:
        age = (today - r.bounced_on).days if r.bounced_on else 0
        for b in buckets:
            if b["max"] is None or age <= b["max"]:
                b["amount"] += float(r.amount or 0.0)
                b["count"]  += 1
                break
    for b in buckets:
        b.pop("max", None)
    return buckets


def monthly_series(
    db: Session, store_ids: list[int], today: date | None = None,
) -> tuple[list[str], list[float], list[float]]:
    """12-month bars for the owner dashboard: per-month recoveries
    (positive) and losses+fraud (negative). Labels are 'YYYY-MM'
    so ApexCharts renders them as a date axis."""
    if today is None:
        today = date.today()
    months = []
    y, m = today.year, today.month
    for _ in range(12):
        months.append((y, m))
        m -= 1
        if m == 0:
            m = 12
            y -= 1
    months.reverse()  # oldest → newest
    labels: list[str] = []
    recoveries: list[float] = []
    losses: list[float] = []
    if not store_ids:
        for (yy, mm) in months:
            labels.append(f"{yy:04d}-{mm:02d}")
            recoveries.append(0.0)
            losses.append(0.0)
        return labels, recoveries, losses
    for (yy, mm) in months:
        s = date(yy, mm, 1)
        e = date(yy, mm, monthrange(yy, mm)[1])
        agg = period_aggregates(db, store_ids, s, e)
        labels.append(f"{yy:04d}-{mm:02d}")
        recoveries.append(round(agg["recoveries"], 2))
        # Combine loss + fraud — both are write-offs from the P&L's POV.
        losses.append(round(agg["losses"] + agg["fraud"], 2))
    return labels, recoveries, losses


def monthly_pl(
    db: Session, store_id: int, year: int, month: int,
) -> float:
    """Signed value for the monthly P&L's Return Check (G/L) line,
    using EXPENSE convention so it slots correctly into the
    expense column on monthly_report (which subtracts from net
    income).

      positive  → net loss for the month (losses + fraud > recoveries)
      negative  → net gain for the month (recoveries > losses + fraud)

    Note: `period_aggregates['net_gl']` uses the OPPOSITE
    convention (positive = gain) because that's what the owner
    dashboard shows. We deliberately negate here so each consumer
    reads the right sign for its context.
    """
    start = date(year, month, 1)
    end = date(year, month, monthrange(year, month)[1])
    agg = period_aggregates(db, [store_id], start, end)
    return -agg["net_gl"]
