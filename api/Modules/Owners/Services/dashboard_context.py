"""Owner dashboard + locations context builders.

Two read-side context builders for the multi-store owner views:

  - `dashboard_context(db, user, period) -> dict[str, Any]`
    Rich metrics for /owner/dashboard. KPI cards with prior-period
    deltas, a fixed 30-day daily-volume area chart, per-company
    donut for the selected window, per-store volume comparison,
    and return-check rollups (period KPIs, aging buckets, 12-month
    bars).

  - `locations_payload(db, user, period, query) -> (rows, total)`
    Per-store rows for /owner/locations. Period-scoped stats
    (transfers, volume, over/short) plus per-company chip list
    so owners see provider mix at a glance. `query` is a
    case-insensitive substring matched against store name.

Both compose the smaller dashboard helpers (`owner_period_window`,
`owner_store_ids`, `owner_kpis`) plus the return-check rollup
Service from PR 62. Pure DB reads — no commits, no side-effects.
"""
from datetime import date, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

from api.Modules.Owners.Services.dashboard import (
    OWNER_TRANSFER_EXCLUDED,
    owner_kpis,
    owner_period_window,
    owner_store_ids,
)
from api.Modules.Owners.Services.return_checks import (
    aging_buckets as return_check_aging_buckets,
    monthly_series as return_check_monthly_series,
    period_aggregates as return_check_period_aggregates,
)
from typing import Any


def dashboard_context(db: Session, user, period: str) -> dict[str, Any]:
    """Rich metrics for the owner dashboard view.

    Mirrors the superadmin dashboard pattern: KPI cards with
    prior-period deltas, a 30-day daily-volume area chart (always
    30d so the trend shape is independent of the selector),
    per-company donut for the selected window, and a per-store
    volume comparison bar.

    Returns a dict suitable for `**kwargs` into render_template.
    """
    from api.Modules.DailyBook.Models import DailyReport
    from api.Modules.Tenancy.Models import Store
    from api.Modules.Transfers.Models import Transfer

    today = date.today()
    start, end, prev_start, prev_end, prev_label = owner_period_window(
        period, today,
    )
    store_ids = owner_store_ids(db, user)
    stores = (
        db.query(Store)
          .filter(Store.id.in_(store_ids))
          .order_by(Store.name)
          .all()
        if store_ids else []
    )

    agg_transfers, agg_volume, agg_over_short = owner_kpis(
        db, store_ids, start, end,
    )
    prev_transfers, prev_volume, prev_over_short = owner_kpis(
        db, store_ids, prev_start, prev_end,
    )

    # 30-day daily-volume series — fixed window regardless of the
    # period selector so the trend shape stays comparable.
    d30_ago = today - timedelta(days=29)
    daily_rows = (
        db.query(
            Transfer.send_date,
            func.count(Transfer.id),
            func.coalesce(func.sum(Transfer.send_amount_cents), 0) / 100.0,
        )
        .filter(
            Transfer.store_id.in_(store_ids),
            Transfer.send_date >= d30_ago,
            Transfer.send_date <= today,
            Transfer.status.notin_(OWNER_TRANSFER_EXCLUDED),
        )
        .group_by(Transfer.send_date)
        .all()
        if store_ids else []
    )
    by_day_vol = {d: float(v or 0) for d, _c, v in daily_rows}
    by_day_cnt = {d: int(c or 0) for d, c, _v in daily_rows}
    series_labels: list[str] = []
    series_volume: list[float] = []
    series_count: list[int] = []
    for i in range(29, -1, -1):
        d = today - timedelta(days=i)
        series_labels.append(d.isoformat())
        series_volume.append(round(by_day_vol.get(d, 0.0), 2))
        series_count.append(by_day_cnt.get(d, 0))

    # Per-company breakdown for the selected period.
    co_rows = (
        db.query(
            Transfer.company,
            func.count(Transfer.id),
            func.coalesce(func.sum(Transfer.send_amount_cents), 0) / 100.0,
            func.coalesce(func.sum(Transfer.fee_cents), 0) / 100.0,
        )
        .filter(
            Transfer.store_id.in_(store_ids),
            Transfer.send_date >= start, Transfer.send_date <= end,
            Transfer.status.notin_(OWNER_TRANSFER_EXCLUDED),
        )
        .group_by(Transfer.company)
        .order_by(
            func.coalesce(func.sum(Transfer.send_amount_cents), 0).desc()
        )
        .all()
        if store_ids else []
    )
    company_breakdown = [
        {"company": (co or "—"), "count": int(cnt),
         "volume": float(v or 0), "fees": float(f or 0)}
        for co, cnt, v, f in co_rows
    ]

    # Per-store volume comparison for the selected period.
    store_rows = (
        db.query(
            Transfer.store_id,
            func.count(Transfer.id),
            func.coalesce(func.sum(Transfer.send_amount_cents), 0) / 100.0,
        )
        .filter(
            Transfer.store_id.in_(store_ids),
            Transfer.send_date >= start, Transfer.send_date <= end,
            Transfer.status.notin_(OWNER_TRANSFER_EXCLUDED),
        )
        .group_by(Transfer.store_id)
        .all()
        if store_ids else []
    )
    store_stat = {
        sid: (int(c), float(v or 0))
        for sid, c, v in store_rows
    }
    # Per-store over/short rollup from DailyReport.over_short over
    # the selected period — same data source the locations view
    # uses. Mirrors the per-store card the SPA renders.
    daily_rows_per_store = (
        db.query(
            DailyReport.store_id,
            func.coalesce(func.sum(DailyReport.over_short_cents), 0) / 100.0,
        )
        .filter(
            DailyReport.store_id.in_(store_ids),
            DailyReport.report_date >= start,
            DailyReport.report_date <= end,
        )
        .group_by(DailyReport.store_id)
        .all()
        if store_ids else []
    )
    over_short_by_store = {
        sid: float(os_v or 0) for sid, os_v in daily_rows_per_store
    }
    store_comparison = []
    store_cards = []
    for s in stores:
        c, v = store_stat.get(s.id, (0, 0.0))
        os_v = over_short_by_store.get(s.id, 0.0)
        store_comparison.append({
            "id": s.id, "name": s.name,
            "count": c, "volume": v,
        })
        # Shape matches `OwnerStoreCard` in frontend/src/api/owner.ts —
        # the SPA owner-dashboard grid renders these directly. Keep
        # `slug` so the route to /owner/store/<slug-or-id> works.
        store_cards.append({
            "id": s.id, "name": s.name, "slug": s.slug,
            "count": c, "volume": v,
            "over_short": os_v,
        })
    store_comparison.sort(key=lambda x: x["volume"], reverse=True)

    # Return-check rollups across the owner's whole umbrella.
    # Owner cares about: outstanding pending balance, period
    # recoveries vs. losses, aging buckets (chase candidates),
    # and a 12-month bar chart of recoveries vs losses+fraud.
    rc_period = return_check_period_aggregates(db, store_ids, start, end)
    rc_aging = return_check_aging_buckets(db, store_ids, today=today)
    rc_labels, rc_recoveries, rc_losses = return_check_monthly_series(
        db, store_ids, today=today,
    )

    return dict(
        user=user, period=period, prev_label=prev_label,
        period_start=start, period_end=end,
        # `store_count` reflects the umbrella size; `stores` is the
        # SPA-shaped card list with per-store count/volume/over_short
        # so the dashboard grid can render without re-fetching.
        store_count=len(stores), stores=store_cards,
        agg_transfers=agg_transfers, agg_volume=agg_volume,
        agg_over_short=agg_over_short,
        agg_transfers_delta=agg_transfers - prev_transfers,
        agg_volume_delta=agg_volume - prev_volume,
        agg_over_short_delta=agg_over_short - prev_over_short,
        series_labels=series_labels, series_volume=series_volume,
        series_count=series_count,
        company_breakdown=company_breakdown,
        store_comparison=store_comparison,
        rc_period=rc_period, rc_aging=rc_aging,
        rc_labels=rc_labels, rc_recoveries=rc_recoveries,
        rc_losses=rc_losses,
    )


def locations_payload(
    db: Session, user, period: str, query: str | None,
) -> tuple[list[dict[str, Any]], int]:
    """Per-store rows for the /owner/locations view.

    Each row has the basic period-scoped stats (transfers,
    volume, over/short) plus a per-company chip list so the
    owner sees provider mix at a glance without drilling in.

    `query` is a substring matched case-insensitively against
    store name.

    Returns `(rows, total_store_count)` where `total_store_count`
    is the unfiltered umbrella size (used by the template to
    distinguish "no stores" from "search returned no results").
    """
    from api.Modules.DailyBook.Models import DailyReport
    from api.Modules.Tenancy.Models import Store
    from api.Modules.Transfers.Models import Transfer

    today = date.today()
    start, end, *_ = owner_period_window(period, today)
    store_ids = owner_store_ids(db, user)
    if not store_ids:
        return [], 0

    base_q = db.query(Store).filter(Store.id.in_(store_ids))
    if query:
        ql = "%{}%".format(query.lower())
        base_q = base_q.filter(func.lower(Store.name).like(ql))
    stores = base_q.order_by(Store.name).all()
    if not stores:
        return [], len(store_ids)

    visible_ids = [s.id for s in stores]

    transfer_rows = (
        db.query(
            Transfer.store_id,
            func.count(Transfer.id),
            func.coalesce(func.sum(Transfer.send_amount_cents), 0) / 100.0,
        )
        .filter(
            Transfer.store_id.in_(visible_ids),
            Transfer.send_date >= start, Transfer.send_date <= end,
            Transfer.status.notin_(OWNER_TRANSFER_EXCLUDED),
        )
        .group_by(Transfer.store_id)
        .all()
    )
    transfer_stat = {
        sid: (int(c), float(v or 0))
        for sid, c, v in transfer_rows
    }

    daily_rows = (
        db.query(
            DailyReport.store_id,
            func.coalesce(func.sum(DailyReport.over_short_cents), 0) / 100.0,
            func.count(DailyReport.id),
        )
        .filter(
            DailyReport.store_id.in_(visible_ids),
            DailyReport.report_date >= start,
            DailyReport.report_date <= end,
        )
        .group_by(DailyReport.store_id)
        .all()
    )
    daily_stat = {
        sid: (float(os_v or 0), int(rc or 0))
        for sid, os_v, rc in daily_rows
    }

    # Per-store, per-company chips (small, ≤ 6 each in practice).
    co_rows = (
        db.query(
            Transfer.store_id, Transfer.company,
            func.count(Transfer.id),
            func.coalesce(func.sum(Transfer.send_amount_cents), 0) / 100.0,
        )
        .filter(
            Transfer.store_id.in_(visible_ids),
            Transfer.send_date >= start, Transfer.send_date <= end,
            Transfer.status.notin_(OWNER_TRANSFER_EXCLUDED),
        )
        .group_by(Transfer.store_id, Transfer.company)
        .all()
    )
    co_by_store: dict[int, list[dict[str, Any]]] = {}
    for sid, co, c, v in co_rows:
        co_by_store.setdefault(sid, []).append({
            "company": (co or "—"),
            "count": int(c),
            "volume": float(v or 0),
        })
    for sid in co_by_store:
        co_by_store[sid].sort(key=lambda x: x["volume"], reverse=True)

    rows: list[dict[str, Any]] = []
    for s in stores:
        c, v = transfer_stat.get(s.id, (0, 0.0))
        os_v, rc = daily_stat.get(s.id, (0.0, 0))
        rows.append({
            "store": s,
            "transfer_count": c,
            "volume": v,
            "over_short": os_v,
            "report_count": rc,
            "companies": co_by_store.get(s.id, []),
        })
    return rows, len(store_ids)
