"""Superadmin platform-health report aggregators.

Pure DB reads — no commits, no side-effects. Each function
returns the `(rows, totals)` shape the legacy templates +
CSV exports expect.
"""
from datetime import date

from sqlalchemy import func
from sqlalchemy.orm import Session
from typing import Any
from api.Core.Clock import utc_now


def _plan_mrr_table() -> dict[tuple[str, str], float]:
    """Build the ``(plan, cycle) -> monthly dollars`` table used by
    MRR/ARR from ``PLAN_CATALOG``.

    This table used to be hard-coded at $49/$99 monthly and
    $490/$990 yearly — pricing the product hasn't sold since the
    numbers were written down.  Against the real $35/$45 it inflated
    every MRR and ARR figure on the superadmin reports by roughly
    40-120%.  Deriving it from the catalog means the pricing page,
    the subscription page, the dashboard MRR tile and these reports
    can no longer disagree.
    """
    from api.Modules.Billing.Services import plan_monthly_cents

    return {
        (plan, cycle): plan_monthly_cents(plan, cycle) / 100.0
        for plan in ("basic", "pro")
        for cycle in ("monthly", "yearly")
    }


# Plan price table used by MRR/ARR, keyed `(plan, billing_cycle)` and
# normalised to monthly dollars. Prices live in PLAN_CATALOG
# (api/Modules/Billing/Services/plans.py) — change them there.
PLAN_MRR: dict[tuple[str, str], float] = _plan_mrr_table()


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
    from api.Modules.Tenancy.Models import Store
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
    from api.Modules.Tenancy.Models import Store
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
    from api.Modules.Tenancy.Models import User
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
    from api.Modules.Tenancy.Models import Store
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
    from api.Modules.Tenancy.Models import Store
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
    from api.Modules.Tenancy.Models import Store
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
    today = utc_now()
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
    from api.Modules.Tenancy.Models import Store
    from api.Modules.Reports.Services.date_helpers import day_end

    trials = (
        db.query(Store)
          .filter(
              Store.plan == "trial",
              Store.created_at <= day_end(d_to),
          )
          .all()
    )
    today = utc_now()
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
    from api.Modules.BankSync.Models import StripeBankAccount
    from api.Modules.Tenancy.Models import Store
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
    from api.Modules.Tenancy.Models import Store
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
    from api.Modules.Tenancy.Models import StoreOwnerLink, User

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
    from api.Modules.Auth.Models import Passkey
    from api.Modules.Tenancy.Models import User

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
    from api.Modules.Auth.Models import PasswordResetToken
    from api.Modules.Tenancy.Models import User
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
    now = utc_now()
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
    from api.Modules.Tenancy.Models import Store
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
    from api.Modules.Tenancy.Models import Store

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


def _stripe_period_unix(d_from: date, d_to: date) -> tuple[int, int]:
    """(gte, lte) Unix timestamps covering [d_from, d_to] inclusive."""
    from api.Modules.Reports.Services.date_helpers import (
        day_end, day_start,
    )
    return (
        int(day_start(d_from).timestamp()),
        int(day_end(d_to).timestamp()),
    )


def _stripe_iter(list_call, *, limit_per_call=100, max_total=500,
                 **kwargs) -> list[Any]:
    """Page through a Stripe `list` API up to `max_total` rows."""
    import stripe
    if not stripe.api_key:
        raise RuntimeError("Stripe API key not configured")
    items: list[Any] = []
    for obj in list_call(**kwargs, limit=limit_per_call).auto_paging_iter():
        items.append(obj)
        if len(items) >= max_total:
            break
    return items


def refunds(
    db: Session,  # unused — Stripe API call
    d_from: date,
    d_to: date,
) -> tuple[list[dict], dict]:
    """Stripe refunds in the period grouped by reason."""
    import stripe
    gte, lte = _stripe_period_unix(d_from, d_to)
    rows: list[dict] = []
    totals = {"count": 0, "amount": 0.0, "stripe_error": ""}
    try:
        objs = _stripe_iter(
            stripe.Refund.list, created={"gte": gte, "lte": lte},
        )
    except Exception as e:
        totals["stripe_error"] = str(e) or type(e).__name__
        return rows, totals
    by_reason: dict[str, dict] = {}
    for r in objs:
        amt = float(r.get("amount", 0) or 0) / 100.0
        reason = (
            (r.get("reason") or "(no reason)")
            .replace("_", " ").title()
        )
        by_reason.setdefault(reason, {"count": 0, "amount": 0.0})
        by_reason[reason]["count"]  += 1
        by_reason[reason]["amount"] += amt
        totals["count"]  += 1
        totals["amount"] += amt
    rows = [
        {"reason": k, "count": v["count"], "amount": v["amount"]}
        for k, v in by_reason.items()
    ]
    rows.sort(key=lambda r: r["amount"], reverse=True)
    return rows, totals


def failed_payments(
    db: Session,
    d_from: date,
    d_to: date,
) -> tuple[list[dict], dict]:
    """Recent failed Stripe charges in the period.

    Stripe doesn't expose a server-side `failed` filter on
    Charge.list, so we pull a capped page and filter client-side.
    """
    import stripe
    gte, lte = _stripe_period_unix(d_from, d_to)
    rows: list[dict] = []
    totals = {"count": 0, "amount": 0.0, "stripe_error": ""}
    try:
        objs = _stripe_iter(
            stripe.Charge.list,
            created={"gte": gte, "lte": lte},
            max_total=500,
        )
    except Exception as e:
        totals["stripe_error"] = str(e) or type(e).__name__
        return rows, totals
    by_reason: dict[str, dict] = {}
    for c in objs:
        if c.get("status") != "failed" and c.get("paid", True):
            continue
        amt = float(c.get("amount", 0) or 0) / 100.0
        outcome = c.get("outcome") or {}
        reason = (
            outcome.get("reason")
            or c.get("failure_message")
            or "(unknown)"
        )[:80]
        by_reason.setdefault(reason, {"count": 0, "amount": 0.0})
        by_reason[reason]["count"]  += 1
        by_reason[reason]["amount"] += amt
        totals["count"]  += 1
        totals["amount"] += amt
    rows = [
        {"reason": k, "count": v["count"], "amount": v["amount"]}
        for k, v in by_reason.items()
    ]
    rows.sort(key=lambda r: r["count"], reverse=True)
    return rows, totals


def payouts(
    db: Session,
    d_from: date,
    d_to: date,
) -> tuple[list[dict], dict]:
    """Stripe payouts to the platform bank account in the period."""
    from datetime import date as _date, datetime
    import stripe
    gte, lte = _stripe_period_unix(d_from, d_to)
    rows: list[dict] = []
    totals = {
        "count": 0, "amount": 0.0, "stripe_error": "",
        "paid": 0, "pending": 0, "failed": 0,
    }
    try:
        objs = _stripe_iter(
            stripe.Payout.list, created={"gte": gte, "lte": lte},
        )
    except Exception as e:
        totals["stripe_error"] = str(e) or type(e).__name__
        return rows, totals
    for p in objs:
        amt = float(p.get("amount", 0) or 0) / 100.0
        arrival_ts = p.get("arrival_date")
        arrival = (
            datetime.utcfromtimestamp(arrival_ts).date()
            if arrival_ts else None
        )
        status = p.get("status", "") or ""
        rows.append({
            "id":      p.get("id", ""),
            "amount":  amt,
            "status":  status.title(),
            "method":  (p.get("method") or "").replace("_", " ").title(),
            "arrival": arrival,
        })
        totals["count"]  += 1
        totals["amount"] += amt
        if status == "paid":    totals["paid"]    += 1
        if status == "pending": totals["pending"] += 1
        if status == "failed":  totals["failed"]  += 1
    rows.sort(key=lambda r: r["arrival"] or _date.min, reverse=True)
    return rows, totals


def dau_mau(
    db: Session,
    d_from: date,
    d_to: date,
) -> tuple[list[dict], dict]:
    """Distinct-user counts per day in the period from LoginEvent.

    Each row = one day with the count of unique users who logged
    in that day. Totals carry MAU (distinct users in period), DAU
    (distinct users today), and stickiness = DAU/MAU * 100.

    Forward-only: LoginEvent only collects rows from when the
    model ships, so periods before that show zeroes.
    """
    from datetime import date as _date, datetime
    from api.Modules.Auth.Models import LoginEvent
    from api.Modules.Reports.Services.date_helpers import (
        day_end, day_start,
    )

    start = day_start(d_from)
    end   = day_end(d_to)

    day_col = func.date(LoginEvent.at)
    per_day_q = (
        db.query(
            day_col,
            func.count(func.distinct(LoginEvent.user_id)),
        )
        .filter(LoginEvent.at >= start, LoginEvent.at <= end)
        .group_by(day_col)
        .order_by(day_col.desc())
        .all()
    )
    rows = [
        {"day": d, "users": int(c or 0)}
        for d, c in per_day_q
    ]

    mau = (
        db.query(func.count(func.distinct(LoginEvent.user_id)))
          .filter(LoginEvent.at >= start, LoginEvent.at <= end)
          .scalar()
    ) or 0
    today_start = datetime.combine(_date.today(), datetime.min.time())
    dau = (
        db.query(func.count(func.distinct(LoginEvent.user_id)))
          .filter(LoginEvent.at >= today_start)
          .scalar()
    ) or 0
    stickiness  = (dau / mau * 100.0) if mau else 0.0
    avg_per_day = (
        sum(r["users"] for r in rows) / len(rows) if rows else 0.0
    )
    totals = {
        "dau":         dau,
        "mau":         int(mau),
        "stickiness":  stickiness,
        "avg_per_day": avg_per_day,
        "active_days": len(rows),
    }
    return rows, totals


def webhook_health(
    db: Session,
    d_from: date,
    d_to: date,
) -> tuple[list[dict], dict]:
    """Inbound Stripe webhook deliveries grouped by status.

    Sourced from WebhookEvent — populated by /webhooks/stripe on
    every delivery (including signature failures). Totals carry
    `ok`, `errors`, `failure_pct`.
    """
    from api.Modules.Webhooks.Models import WebhookEvent
    from api.Modules.Reports.Services.date_helpers import (
        day_end, day_start,
    )

    rows_q = (
        db.query(WebhookEvent.status, func.count(WebhookEvent.id))
          .filter(
              WebhookEvent.received_at >= day_start(d_from),
              WebhookEvent.received_at <= day_end(d_to),
          )
          .group_by(WebhookEvent.status)
          .all()
    )
    rows: list[dict] = []
    totals = {"count": 0, "ok": 0, "errors": 0}
    for status, count in rows_q:
        c = int(count or 0)
        rows.append({
            "status":     (status or "unknown").replace("_", " ").title(),
            "status_key": status or "",
            "count":      c,
        })
        totals["count"] += c
        if status == "ok":
            totals["ok"] += c
        else:
            totals["errors"] += c
    rows.sort(key=lambda r: r["count"], reverse=True)
    totals["failure_pct"] = (
        totals["errors"] / totals["count"] * 100.0
        if totals["count"] else 0.0
    )
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
    from api.Modules.Tenancy.Models import Store
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
