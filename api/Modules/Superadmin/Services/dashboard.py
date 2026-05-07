"""Superadmin platform dashboard context builder.

Big read-side aggregator that powers the `/superadmin/controls`
Dashboard tab. Returns the kwargs dict the template expects:

  - KPI counters (total stores, active, trial, paid, inactive)
    with 30-day deltas (new vs prior 30, churn vs prior 30)
  - 90-day daily signup trend split by direct vs referral
  - plan distribution (Trial / Basic / Pro / Inactive)
  - MRR breakdown — yearly subscribers amortised to /12
  - referral leaderboard (top 5 by redemption count)
  - 30-day transfer volume rolled up by company (top 6)
  - merged activity feed (signups + cancels, newest first, capped 12)
  - full store list ordered by signup date

`compute_mrr` is exposed separately so the operator-billing page
can stay in lockstep with the dashboard's MRR math.

Pure DB read — no commits, no side-effects.
"""
from datetime import date, datetime, timedelta

from sqlalchemy import case, func
from sqlalchemy.orm import Session


# Plan pricing in dollars. Yearly buckets are amortised to /12
# when summed into MRR.
_BASIC_MONTHLY_PRICE = 35
_BASIC_YEARLY_PRICE = 350
_PRO_MONTHLY_PRICE = 45
_PRO_YEARLY_PRICE = 420


def compute_mrr(
    basic_monthly: int, basic_yearly: int,
    pro_monthly: int, pro_yearly: int,
) -> tuple[int, int, int, int, int]:
    """Return MRR components and total from subscriber counts.

    Yearly subscribers are amortised to /12.
    Prices: Basic $35/mo or $350/yr; Pro $45/mo or $420/yr.

    Returns `(basic_monthly_mrr, basic_yearly_mrr,
              pro_monthly_mrr, pro_yearly_mrr, total)`.
    """
    bm = basic_monthly * _BASIC_MONTHLY_PRICE
    by_ = round(basic_yearly * _BASIC_YEARLY_PRICE / 12)
    pm = pro_monthly * _PRO_MONTHLY_PRICE
    py_ = round(pro_yearly * _PRO_YEARLY_PRICE / 12)
    return bm, by_, pm, py_, bm + by_ + pm + py_


def superadmin_dashboard_context(db: Session) -> dict:
    """Platform-wide BI metrics for the superadmin Dashboard tab.

    Returns the kwargs dict that `dashboard_superadmin.html`
    expects.
    """
    from app import ReferralCode, Store, Transfer

    now = datetime.utcnow()
    today_d = date.today()
    d30_ago = now - timedelta(days=30)
    d60_ago = now - timedelta(days=60)
    d90_ago = now - timedelta(days=90)

    # Plan + cycle distribution. Single GROUP BY → split into the
    # eight buckets the dashboard needs.
    plan_rows = (
        db.query(
            Store.plan, Store.billing_cycle, func.count(Store.id),
        )
        .group_by(Store.plan, Store.billing_cycle)
        .all()
    )
    basic_monthly = basic_yearly = pro_monthly = pro_yearly = 0
    trial_count = inactive_count = 0
    for p, cycle, n in plan_rows:
        if p == "basic":
            if cycle == "yearly":
                basic_yearly += n
            else:
                basic_monthly += n
        elif p == "pro":
            if cycle == "yearly":
                pro_yearly += n
            else:
                pro_monthly += n
        elif p == "trial":
            trial_count += n
        elif p == "inactive":
            inactive_count += n

    basic_count = basic_monthly + basic_yearly
    pro_count = pro_monthly + pro_yearly
    paid_count = basic_count + pro_count
    total_stores = db.query(Store).count()
    active_count = db.query(Store).filter_by(is_active=True).count()

    (basic_monthly_mrr, basic_yearly_mrr,
     pro_monthly_mrr, pro_yearly_mrr,
     estimated_mrr) = compute_mrr(
        basic_monthly, basic_yearly, pro_monthly, pro_yearly,
    )

    # New-store + churn KPI deltas (30d vs prior 30d).
    new_stores_30d = (
        db.query(Store).filter(Store.created_at >= d30_ago).count()
    )
    new_stores_prev30 = (
        db.query(Store)
          .filter(
              Store.created_at >= d60_ago,
              Store.created_at < d30_ago,
          )
          .count()
    )
    new_stores_delta = new_stores_30d - new_stores_prev30

    churn_30d = (
        db.query(Store)
          .filter(
              Store.canceled_at.isnot(None),
              Store.canceled_at >= d30_ago,
          )
          .count()
    )
    churn_prev30 = (
        db.query(Store)
          .filter(
              Store.canceled_at.isnot(None),
              Store.canceled_at >= d60_ago,
              Store.canceled_at < d30_ago,
          )
          .count()
    )
    churn_delta = churn_30d - churn_prev30

    # 90-day daily signup series, split by direct vs referral.
    # SQLite's date(col) returns an ISO string; Postgres' returns
    # a date — normalize to ISO strings for the chart.
    signup_rows = (
        db.query(
            func.date(Store.created_at).label("d"),
            func.sum(case(
                (Store.referred_by_code_id.is_(None), 1),
                else_=0,
            )).label("direct"),
            func.sum(case(
                (Store.referred_by_code_id.isnot(None), 1),
                else_=0,
            )).label("referral"),
        )
        .filter(Store.created_at >= d90_ago)
        .group_by("d")
        .all()
    )
    by_day = {}
    for d_val, direct, referral in signup_rows:
        key = (
            d_val.isoformat() if hasattr(d_val, "isoformat")
            else str(d_val)
        )
        by_day[key] = (int(direct or 0), int(referral or 0))

    signup_labels: list[str] = []
    signup_direct: list[int] = []
    signup_referral: list[int] = []
    for i in range(89, -1, -1):
        d = today_d - timedelta(days=i)
        key = d.isoformat()
        direct, referral = by_day.get(key, (0, 0))
        signup_labels.append(key)
        signup_direct.append(direct)
        signup_referral.append(referral)

    plan_dist = [
        {"label": "Trial",    "count": trial_count},
        {"label": "Basic",    "count": basic_count},
        {"label": "Pro",      "count": pro_count},
        {"label": "Inactive", "count": inactive_count},
    ]

    # Referral leaderboard: top 5 by redemption count.
    top_referrers_raw = (
        db.query(ReferralCode, Store)
          .join(Store, ReferralCode.owner_store_id == Store.id)
          .filter(ReferralCode.redeemed_count > 0)
          .order_by(ReferralCode.redeemed_count.desc())
          .limit(5)
          .all()
    )
    top_referrers = [
        {
            "store_name": s.name,
            "slug": s.slug,
            "code": rc.code,
            "redeemed": rc.redeemed_count,
            "reward_total_cents": (
                rc.redeemed_count * rc.reward_self_cents
            ),
        }
        for rc, s in top_referrers_raw
    ]
    referral_signups = (
        db.query(Store)
          .filter(Store.referred_by_code_id.isnot(None))
          .count()
    )
    direct_signups = total_stores - referral_signups

    # 30-day transfer volume by company (top 6).
    volume_rows = (
        db.query(
            Transfer.company,
            func.count(Transfer.id),
            func.coalesce(func.sum(Transfer.send_amount), 0.0),
        )
        .filter(
            Transfer.created_at >= d30_ago,
            Transfer.status.notin_(["Canceled", "Rejected"]),
        )
        .group_by(Transfer.company)
        .order_by(
            func.coalesce(func.sum(Transfer.send_amount), 0.0).desc(),
        )
        .limit(6)
        .all()
    )
    volume_by_company = [
        {"company": co or "—", "count": int(cnt),
         "total": float(tot or 0)}
        for co, cnt, tot in volume_rows
    ]
    total_volume_30d = sum(v["total"] for v in volume_by_company)
    total_transfers_30d = sum(v["count"] for v in volume_by_company)

    # Merged activity feed — signups + cancels, newest first,
    # capped at 12 so the card stays scannable.
    recent_signups = (
        db.query(Store).order_by(Store.created_at.desc()).limit(10).all()
    )
    recent_cancels = (
        db.query(Store)
          .filter(Store.canceled_at.isnot(None))
          .order_by(Store.canceled_at.desc())
          .limit(10)
          .all()
    )
    activity: list[dict] = []
    for s in recent_signups:
        activity.append({
            "when": s.created_at,
            "kind": "signup",
            "store_name": s.name,
            "detail": (
                "via referral" if s.referred_by_code_id
                else "direct signup"
            ),
            "plan": s.plan,
        })
    for s in recent_cancels:
        activity.append({
            "when": s.canceled_at,
            "kind": "cancel",
            "store_name": s.name,
            "detail": "canceled subscription",
            "plan": s.plan,
        })
    activity.sort(
        key=lambda a: a["when"] or datetime.min, reverse=True,
    )
    activity = activity[:12]

    stores = (
        db.query(Store).order_by(Store.created_at.desc()).all()
    )

    return dict(
        total_stores=total_stores, active_count=active_count,
        trial_count=trial_count, paid_count=paid_count,
        estimated_mrr=estimated_mrr, inactive_count=inactive_count,
        new_stores_30d=new_stores_30d,
        new_stores_delta=new_stores_delta,
        churn_30d=churn_30d, churn_delta=churn_delta,
        basic_monthly=basic_monthly, basic_yearly=basic_yearly,
        pro_monthly=pro_monthly, pro_yearly=pro_yearly,
        basic_monthly_mrr=basic_monthly_mrr,
        basic_yearly_mrr=basic_yearly_mrr,
        pro_monthly_mrr=pro_monthly_mrr,
        pro_yearly_mrr=pro_yearly_mrr,
        basic_count=basic_count, pro_count=pro_count,
        signup_labels=signup_labels,
        signup_direct=signup_direct,
        signup_referral=signup_referral,
        plan_dist=plan_dist,
        volume_by_company=volume_by_company,
        total_volume_30d=total_volume_30d,
        total_transfers_30d=total_transfers_30d,
        top_referrers=top_referrers,
        direct_signups=direct_signups,
        referral_signups=referral_signups,
        activity=activity,
        stores=stores,
    )
