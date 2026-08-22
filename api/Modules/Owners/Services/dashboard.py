"""Multi-store owner dashboard — period windows, store list, KPIs.

Three small read-side helpers that the owner dashboard / locations
pages share:

  - `owner_period_window(period, today)` — pure date math
    mapping a `today|month|year` selector to current + prior
    windows so KPI deltas are like-for-like.
  - `owner_store_ids(db, user)` — store IDs the owner is linked
    to via `StoreOwnerLink`. Empty list when the owner has no
    stores yet.
  - `owner_kpis(db, store_ids, start, end)` — aggregate
    (transfer_count, volume, over_short) across the umbrella +
    window. Excludes Canceled / Rejected transfers.

The richer `owner_dashboard_context` / `owner_locations_payload`
functions stay in app.py for now — they pull in the return-check
rollup helpers (`_return_check_*`) that aren't extracted yet.
"""
from datetime import date, timedelta
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session


# Status values excluded from owner-facing transfer rollups so a
# canceled transfer doesn't inflate volume.
OWNER_TRANSFER_EXCLUDED: list[str] = ["Canceled", "Rejected"]


def owner_period_window(
    period: str, today: date,
) -> tuple[date, date, date, date, str]:
    """Map a `today|month|year` selector to current + prior windows.

    Returns `(start, end, prev_start, prev_end, prev_label)`. The
    prior window has the same number of days as the current and
    ends the day before the current one starts, so KPI deltas are
    like-for-like.

    Default (and any unrecognized value) is `today` — single-day
    window with `vs yesterday` for the delta label.
    """
    if period == "month":
        start = today.replace(day=1)
        end = today
        days = (end - start).days
        prev_end = start - timedelta(days=1)
        prev_start = prev_end - timedelta(days=days)
        return start, end, prev_start, prev_end, "vs prior month"
    if period == "year":
        start = date(today.year, 1, 1)
        end = today
        days = (end - start).days
        prev_end = start - timedelta(days=1)
        prev_start = prev_end - timedelta(days=days)
        return start, end, prev_start, prev_end, "vs prior year"
    # default: today
    return (
        today, today,
        today - timedelta(days=1), today - timedelta(days=1),
        "vs yesterday",
    )


def owner_store_ids(db: Session, user: Any) -> list[int]:
    """Store IDs the given owner is linked to, sorted. Empty if none.

    Thin ``User``-taking wrapper over the canonical repository query
    ``store_links.store_ids_for_owner(db, owner_id)`` — kept because
    the seven controller call sites pass a ``User`` and expect an
    ordered ``list``. Sorted for deterministic output (the repo
    returns an unordered set)."""
    from api.Modules.Owners.Repositories import store_ids_for_owner
    return sorted(store_ids_for_owner(db, user.id))


def owner_kpis(
    db: Session, store_ids: list[int], start: date, end: date,
) -> tuple[int, float, float]:
    """Aggregate (transfer_count, volume, over_short) across the
    given stores and date window.

    Excludes canceled / rejected transfers so the volume number
    matches what the owner expects in the operations view.

    Returns `(0, 0.0, 0.0)` for an empty store_ids list — empty
    umbrella means no metrics rather than an error.
    """
    if not store_ids:
        return 0, 0.0, 0.0
    from api.Modules.DailyBook.Models import DailyReport
    from api.Modules.Transfers.Models import Transfer
    tx_count = (
        db.query(Transfer)
          .filter(
              Transfer.store_id.in_(store_ids),
              Transfer.send_date >= start,
              Transfer.send_date <= end,
              Transfer.status.notin_(OWNER_TRANSFER_EXCLUDED),
          )
          .count()
    )
    vol = (
        db.query(func.coalesce(func.sum(Transfer.send_amount_cents), 0) / 100.0)
          .filter(
              Transfer.store_id.in_(store_ids),
              Transfer.send_date >= start,
              Transfer.send_date <= end,
              Transfer.status.notin_(OWNER_TRANSFER_EXCLUDED),
          )
          .scalar() or 0.0
    )
    os_total = (
        db.query(func.coalesce(func.sum(DailyReport.over_short_cents), 0) / 100.0)
          .filter(
              DailyReport.store_id.in_(store_ids),
              DailyReport.report_date >= start,
              DailyReport.report_date <= end,
          )
          .scalar() or 0.0
    )
    return int(tx_count), float(vol), float(os_total)
