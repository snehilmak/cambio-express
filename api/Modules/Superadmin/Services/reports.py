"""Superadmin platform-health report aggregators.

Pure DB reads — no commits, no side-effects. Each function
returns the `(rows, totals)` shape the legacy templates +
CSV exports expect.
"""
from datetime import date

from sqlalchemy import func
from sqlalchemy.orm import Session


# Hard-coded plan price table. Used by MRR/ARR. When Stripe pricing
# changes, update here. Yearly prices are normalised to monthly
# equivalents for the MRR sum.
PLAN_MRR: dict[tuple[str, str], float] = {
    ("basic", "monthly"): 49.0,
    ("basic", "yearly"):  490.0 / 12.0,
    ("pro",   "monthly"): 99.0,
    ("pro",   "yearly"):  990.0 / 12.0,
}


def _plan_label(plan: str | None) -> str:
    """Display-cased plan name; '(unknown)' for NULL/empty."""
    return (plan or "(unknown)").title()


def active_stores_by_plan(
    db: Session,
    d_from: date,  # unused — adoption is point-in-time
    d_to: date,
) -> tuple[list[dict], dict]:
    """Headcount of stores per plan at end of period.

    Counts stores created on or before `d_to` (i.e. existing
    stores at end of period, not just newcomers). `d_from` is
    intentionally unused — this is a point-in-time view.
    """
    from app import Store
    from api.Modules.Reports.Services.date_helpers import day_end

    q = (
        db.query(Store.plan, func.count(Store.id))
          .filter(Store.created_at <= day_end(d_to))
          .group_by(Store.plan)
          .all()
    )
    rows = [
        {"plan": _plan_label(plan), "count": int(c or 0)}
        for plan, c in q
    ]
    rows.sort(key=lambda r: r["count"], reverse=True)
    totals = {
        "count": sum(r["count"] for r in rows),
        "plans": len(rows),
    }
    return rows, totals


def signup_funnel(
    db: Session,
    d_from: date,
    d_to: date,
) -> tuple[list[dict], dict]:
    """Stores created in the period bucketed by current plan.

    Useful for measuring signup → activation success.
    """
    from app import Store
    from api.Modules.Reports.Services.date_helpers import (
        day_end, day_start,
    )

    q = (
        db.query(Store.plan, func.count(Store.id))
          .filter(
              Store.created_at >= day_start(d_from),
              Store.created_at <= day_end(d_to),
          )
          .group_by(Store.plan)
          .all()
    )
    rows = [
        {"plan": _plan_label(plan), "count": int(c or 0)}
        for plan, c in q
    ]
    rows.sort(key=lambda r: r["count"], reverse=True)
    totals = {"count": sum(r["count"] for r in rows)}
    return rows, totals


def login_activity(
    db: Session,
    d_from: date,
    d_to: date,
) -> tuple[list[dict], dict]:
    """Per-role unique login counts in the period.

    Drives the platform-health DAU / MAU dashboards once we
    have a per-day login log; for now it surfaces the per-role
    split using `User.last_login_at`.
    """
    from app import User
    from api.Modules.Reports.Services.date_helpers import (
        day_end, day_start,
    )

    q = (
        db.query(User.role, func.count(User.id))
          .filter(
              User.last_login_at >= day_start(d_from),
              User.last_login_at <= day_end(d_to),
          )
          .group_by(User.role)
          .all()
    )
    rows = [
        {"role": (role or "(unknown)").title(), "count": int(c or 0)}
        for role, c in q
    ]
    rows.sort(key=lambda r: r["count"], reverse=True)
    totals = {"count": sum(r["count"] for r in rows)}
    return rows, totals


def mrr_arr(
    db: Session,
    d_from: date,  # unused — point-in-time at end of period
    d_to: date,
) -> tuple[list[dict], dict]:
    """MRR + ARR by plan/cycle. Counts active (basic/pro) stores
    at end of period (created_at <= d_to). `d_from` is unused —
    this is a point-in-time snapshot.
    """
    from app import Store
    from api.Modules.Reports.Services.date_helpers import day_end

    q = (
        db.query(Store.plan, Store.billing_cycle, func.count(Store.id))
          .filter(
              Store.created_at <= day_end(d_to),
              Store.plan.in_(["basic", "pro"]),
          )
          .group_by(Store.plan, Store.billing_cycle)
          .all()
    )
    rows: list[dict] = []
    totals = {"mrr": 0.0, "stores": 0}
    for plan, cycle, count in q:
        c = int(count or 0)
        cycle = cycle or "monthly"
        per_store_mrr = PLAN_MRR.get((plan, cycle), 0.0)
        mrr = per_store_mrr * c
        rows.append({
            "plan":   plan.title(),
            "cycle":  cycle.title(),
            "stores": c,
            "mrr":    mrr,
            "arr":    mrr * 12.0,
        })
        totals["mrr"]    += mrr
        totals["stores"] += c
    rows.sort(key=lambda r: r["mrr"], reverse=True)
    totals["arr"] = totals["mrr"] * 12.0
    return rows, totals


def conversion_rate(
    db: Session,
    d_from: date,
    d_to: date,
) -> tuple[list[dict], dict]:
    """For stores that signed up in the period: how many graduated
    from trial to paid by today? Single summary row.
    """
    from app import Store
    from api.Modules.Reports.Services.date_helpers import (
        day_end, day_start,
    )

    cohort = (
        db.query(Store)
          .filter(
              Store.created_at >= day_start(d_from),
              Store.created_at <= day_end(d_to),
          )
          .all()
    )
    total = len(cohort)
    paid  = sum(1 for s in cohort if s.plan in ("basic", "pro"))
    trial = sum(1 for s in cohort if s.plan == "trial")
    inactive = total - paid - trial
    rate = (paid / total * 100.0) if total else 0.0
    rows = [
        {"label": "Paid",     "count": paid,     "tone": "neon"},
        {"label": "Trial",    "count": trial,    "tone": "muted"},
        {"label": "Inactive", "count": inactive, "tone": "muted"},
    ]
    totals = {"total": total, "paid": paid, "rate": rate, "count": total}
    return rows, totals


def time_to_convert(
    db: Session,
    d_from: date,
    d_to: date,
) -> tuple[list[dict], dict]:
    """For paid stores that signed up in the period, days from
    signup (created_at) to today as a proxy for "activation
    delay" — we don't yet log the exact trial→paid timestamp.
    """
    from datetime import datetime
    from app import Store
    from api.Modules.Reports.Services.date_helpers import (
        day_end, day_start,
    )

    paid = (
        db.query(Store)
          .filter(
              Store.created_at >= day_start(d_from),
              Store.created_at <= day_end(d_to),
              Store.plan.in_(["basic", "pro"]),
          )
          .all()
    )
    today = datetime.utcnow()
    rows: list[dict] = []
    for s in paid:
        if not s.created_at:
            continue
        rows.append({
            "slug":       s.slug,
            "name":       s.name,
            "signed_up":  s.created_at.date(),
            "plan":       (s.plan or "").title(),
            "days":       (today - s.created_at).days,
        })
    rows.sort(key=lambda r: r["days"])
    avg = (sum(r["days"] for r in rows) / len(rows)) if rows else 0.0
    totals = {"count": len(rows), "avg_days": avg}
    return rows, totals


def trial_expiry_timing(
    db: Session,
    d_from: date,  # unused — point-in-time at end-of-period
    d_to: date,
) -> tuple[list[dict], dict]:
    """Bucket trial stores by where they are in their trial window
    (counted at end-of-period). Helps see whether stores convert
    early, late, or roll into expiry. `d_from` is unused — point-
    in-time at end-of-period.
    """
    from datetime import datetime
    from app import Store
    from api.Modules.Reports.Services.date_helpers import day_end

    trials = (
        db.query(Store)
          .filter(
              Store.plan == "trial",
              Store.created_at <= day_end(d_to),
          )
          .all()
    )
    today = datetime.utcnow()
    buckets = {
        "≤ 7 days into trial":         0,
        "8–14 days":                   0,
        "15–21 days":                  0,
        "22+ days":                    0,
        "Trial expired (no upgrade)":  0,
    }
    for s in trials:
        if not s.created_at:
            continue
        days = (today - s.created_at).days
        if s.trial_ends_at and today > s.trial_ends_at:
            buckets["Trial expired (no upgrade)"] += 1
        elif days <= 7:
            buckets["≤ 7 days into trial"] += 1
        elif days <= 14:
            buckets["8–14 days"] += 1
        elif days <= 21:
            buckets["15–21 days"] += 1
        else:
            buckets["22+ days"] += 1
    rows = [
        {"bucket": k, "count": v}
        for k, v in buckets.items() if v > 0
    ]
    totals = {
        "count":        sum(b["count"] for b in rows),
        "trials_total": len(trials),
    }
    return rows, totals


def churn_cohort(
    db: Session,
    d_from: date,
    d_to: date,
) -> tuple[list[dict], dict]:
    """Stores cancelled in the period bucketed by signup-month
    cohort. Each row: cohort label + count cancelled + paid stores
    that survived (still active from that cohort).

    Active counts are pulled in a single GROUP BY query (single
    round-trip per call regardless of cohort count).
    """
    from app import Store
    from api.Modules.Reports.Services.date_helpers import (
        day_end, day_start,
    )

    cancelled_q = (
        db.query(Store)
          .filter(
              Store.canceled_at >= day_start(d_from),
              Store.canceled_at <= day_end(d_to),
          )
          .all()
    )
    by_cohort: dict[str, dict] = {}
    for s in cancelled_q:
        if not s.created_at:
            continue
        cohort = s.created_at.strftime("%Y-%m")
        by_cohort.setdefault(cohort, {"cancelled": 0, "active": 0})
        by_cohort[cohort]["cancelled"] += 1

    if by_cohort:
        cohort_expr = func.strftime("%Y-%m", Store.created_at)
        active_q = (
            db.query(cohort_expr, func.count(Store.id))
              .filter(
                  Store.canceled_at.is_(None),
                  Store.plan.in_(["basic", "pro"]),
                  cohort_expr.in_(list(by_cohort.keys())),
              )
              .group_by(cohort_expr)
              .all()
        )
        for cohort, count in active_q:
            if cohort in by_cohort:
                by_cohort[cohort]["active"] = int(count or 0)

    rows = [
        {
            "cohort":    cohort,
            "cancelled": v["cancelled"],
            "active":    v["active"],
            "churn_pct": (
                v["cancelled"] / (v["cancelled"] + v["active"]) * 100.0
                if (v["cancelled"] + v["active"]) else 0.0
            ),
        }
        for cohort, v in by_cohort.items()
    ]
    rows.sort(key=lambda r: r["cohort"], reverse=True)
    totals = {
        "cancelled": sum(r["cancelled"] for r in rows),
        "active":    sum(r["active"]    for r in rows),
    }
    return rows, totals
