"""Superadmin platform-health report aggregators.

Pure DB reads — no commits, no side-effects. Each function
returns the `(rows, totals)` shape the legacy templates +
CSV exports expect.
"""
from datetime import date

from sqlalchemy import func
from sqlalchemy.orm import Session


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
