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


def bank_sync_adoption(
    db: Session,
    d_from: date,  # unused — adoption is point-in-time
    d_to: date,
) -> tuple[list[dict], dict]:
    """Stores with at least one connected `StripeBankAccount`,
    grouped by plan. Period filter is ignored — adoption is
    point-in-time at end of period (we don't have a per-day
    history of when each account connected).
    """
    from app import Store, StripeBankAccount
    from api.Modules.Reports.Services.date_helpers import day_end

    connected_ids = {
        sid for (sid,) in
        db.query(StripeBankAccount.store_id).distinct().all()
    }
    all_stores = (
        db.query(Store)
          .filter(Store.created_at <= day_end(d_to))
          .all()
    )
    by_plan: dict[str, dict] = {}
    for s in all_stores:
        plan = _plan_label(s.plan)
        b = by_plan.setdefault(plan, {"connected": 0, "total": 0})
        b["total"] += 1
        if s.id in connected_ids:
            b["connected"] += 1
    rows = [
        {
            "plan":      plan,
            "connected": v["connected"],
            "total":     v["total"],
            "rate_pct": (
                v["connected"] / v["total"] * 100.0
                if v["total"] else 0.0
            ),
        }
        for plan, v in by_plan.items()
    ]
    rows.sort(key=lambda r: r["rate_pct"], reverse=True)
    totals = {
        "connected": sum(r["connected"] for r in rows),
        "total":     sum(r["total"]     for r in rows),
    }
    totals["rate_pct"] = (
        totals["connected"] / totals["total"] * 100.0
        if totals["total"] else 0.0
    )
    return rows, totals


def tv_display_adoption(
    db: Session,
    d_from: date,  # unused — point-in-time
    d_to: date,
) -> tuple[list[dict], dict]:
    """Stores with the TV-display add-on enabled
    (`Store.addons` contains 'tv_display').
    """
    from app import Store
    from api.Modules.Reports.Services.date_helpers import day_end

    stores = (
        db.query(Store)
          .filter(Store.created_at <= day_end(d_to))
          .all()
    )
    enabled = [
        s for s in stores if "tv_display" in (s.addons or "")
    ]
    rows = [
        {
            "slug": s.slug,
            "name": s.name,
            "plan": (s.plan or "").title(),
        }
        for s in enabled
    ]
    rows.sort(key=lambda r: r["name"].lower())
    totals = {"count": len(enabled), "total_stores": len(stores)}
    return rows, totals


def owner_adoption(
    db: Session,
    d_from: date,  # unused — point-in-time
    d_to: date,
) -> tuple[list[dict], dict]:
    """Owners with multiple linked stores (umbrella ownership).
    Each row: owner display label + email + linked-store count.
    Single-store owners are excluded.
    """
    from app import StoreOwnerLink, User

    rows_q = (
        db.query(
            StoreOwnerLink.owner_id,
            func.count(StoreOwnerLink.store_id),
        )
        .group_by(StoreOwnerLink.owner_id)
        .all()
    )
    multi = [(oid, c) for oid, c in rows_q if (c or 0) > 1]
    if not multi:
        return [], {"count": 0, "owners": 0}

    user_ids = [oid for oid, _ in multi]
    users = {
        u.id: u
        for u in db.query(User).filter(User.id.in_(user_ids)).all()
    }
    rows = []
    for oid, count in multi:
        u = users.get(oid)
        rows.append({
            "owner":  (u.full_name or u.username) if u else f"User #{oid}",
            "email":  (u.email or u.username) if u else "",
            "stores": int(count or 0),
        })
    rows.sort(key=lambda r: r["stores"], reverse=True)
    totals = {
        "count":  len(rows),
        "owners": len(rows),
        "stores": sum(r["stores"] for r in rows),
    }
    return rows, totals


def passkey_adoption(
    db: Session,
    d_from: date,  # unused — point-in-time
    d_to: date,
) -> tuple[list[dict], dict]:
    """Users with at least one passkey, grouped by role.
    Helps gauge rollout of passwordless auth.
    """
    from app import Passkey, User

    user_ids = {
        uid for (uid,) in db.query(Passkey.user_id).distinct().all()
    }
    total_users = db.query(User).count()
    rate_pct = (
        len(user_ids) / total_users * 100.0 if total_users else 0.0
    )
    if not user_ids:
        return [], {
            "count": 0,
            "users_with_passkey": 0,
            "total_users": total_users,
            "rate_pct": rate_pct,
        }
    users = db.query(User).filter(User.id.in_(user_ids)).all()
    by_role: dict[str, int] = {}
    for u in users:
        r = (u.role or "(unknown)").title()
        by_role[r] = by_role.get(r, 0) + 1
    rows = [
        {"role": role, "count": count}
        for role, count in by_role.items()
    ]
    rows.sort(key=lambda r: r["count"], reverse=True)
    totals = {
        "count":              len(user_ids),
        "users_with_passkey": len(user_ids),
        "total_users":        total_users,
        "rate_pct":           rate_pct,
    }
    return rows, totals


def password_resets(
    db: Session,
    d_from: date,
    d_to: date,
) -> tuple[list[dict], dict]:
    """Password-reset token activity in the period.

    Each row: created_at + username + role + status (Used /
    Expired / Open). Tokens are pre-loaded with their users in
    a single IN-query (avoiding N+1).
    """
    from datetime import datetime
    from app import PasswordResetToken, User
    from api.Modules.Reports.Services.date_helpers import (
        day_end, day_start,
    )

    tokens = (
        db.query(PasswordResetToken)
          .filter(
              PasswordResetToken.created_at >= day_start(d_from),
              PasswordResetToken.created_at <= day_end(d_to),
          )
          .order_by(PasswordResetToken.created_at.desc())
          .all()
    )
    user_ids = {t.user_id for t in tokens if t.user_id}
    users = (
        {u.id: u for u in db.query(User).filter(User.id.in_(user_ids)).all()}
        if user_ids else {}
    )
    now = datetime.utcnow()
    rows: list[dict] = []
    used = expired = open_count = 0
    for t in tokens:
        if t.used_at:
            status = "Used"; used += 1
        elif t.expires_at and now > t.expires_at:
            status = "Expired"; expired += 1
        else:
            status = "Open"; open_count += 1
        u = users.get(t.user_id) if t.user_id else None
        rows.append({
            "created_at": t.created_at,
            "username":   u.username if u else "(deleted)",
            "role":       u.role if u else "",
            "status":     status,
        })
    totals = {
        "count":   len(tokens),
        "used":    used,
        "expired": expired,
        "open":    open_count,
    }
    return rows, totals


def suspended_stores(
    db: Session,
    d_from: date,  # unused — point-in-time
    d_to: date,
) -> tuple[list[dict], dict]:
    """Stores currently suspended (`is_active=False`) or marked
    inactive (`plan='inactive'`). Point-in-time at end of period.
    """
    from sqlalchemy import or_
    from app import Store
    from api.Modules.Reports.Services.date_helpers import day_end

    suspended = (
        db.query(Store)
          .filter(
              Store.created_at <= day_end(d_to),
              or_(Store.is_active == False, Store.plan == "inactive"),
          )
          .all()
    )
    rows: list[dict] = []
    for s in suspended:
        reason = []
        if not s.is_active:
            reason.append("suspended")
        if s.plan == "inactive":
            reason.append("plan inactive")
        rows.append({
            "slug":        s.slug,
            "name":        s.name,
            "plan":        (s.plan or "").title(),
            "reason":      " · ".join(reason),
            "canceled_at": s.canceled_at,
        })
    rows.sort(key=lambda r: r["name"].lower())
    totals = {"count": len(rows)}
    return rows, totals


def retention_queue(
    db: Session,
    d_from: date,  # unused — point-in-time
    d_to: date,
) -> tuple[list[dict], dict]:
    """Stores in the 180-day data-retention delete window (those
    with `data_retention_until` set). Once the date passes,
    `purge_expired_stores` wipes them. Point-in-time.
    """
    from datetime import date as _date
    from app import Store

    stores = (
        db.query(Store)
          .filter(Store.data_retention_until.isnot(None))
          .order_by(Store.data_retention_until.asc())
          .all()
    )
    today = _date.today()
    rows: list[dict] = []
    for s in stores:
        until = (
            s.data_retention_until.date()
            if hasattr(s.data_retention_until, "date")
            else s.data_retention_until
        )
        days_left = (until - today).days
        rows.append({
            "slug":           s.slug,
            "name":           s.name,
            "plan":           (s.plan or "").title(),
            "until":          until,
            "days_left":      days_left,
            "ready_to_purge": days_left <= 0,
        })
    totals = {
        "count":          len(rows),
        "ready_to_purge": sum(1 for r in rows if r["ready_to_purge"]),
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
