"""Peak-hour heatmap aggregation.

Buckets a store's transfers into a 7×24 grid keyed on
(day_of_week, hour-of-day) in the store's local timezone, so
the SPA can render a calendar-week heatmap showing when the
store is busiest. Optionally overlays the configured
``store_hours`` window so out-of-hours activity stands out.

Python-side bucketing keeps the SQL portable across SQLite +
Postgres. Typical store load (~hundreds of transfers/month)
fits comfortably in memory.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy.orm import Session

from api.Modules.Tenancy.Models import Store
from api.Modules.Transfers.Models import Transfer


def compute_peak_hours(
    db: Session,
    *,
    store_id: int,
    start: datetime,
    end: datetime,
) -> dict[str, Any]:
    """Return the 7×24 grid + headline counts for the picked
    window.

    Shape:
      {
        "from_date":       "YYYY-MM-DD",
        "to_date":         "YYYY-MM-DD",
        "timezone":        str,
        "total_transfers": int,
        "max_count":       int,        # normalization hint
        "grid":            [[int×24] ×7],  # [Mon..Sun][0..23]
        "busiest": {
          "day_of_week": int (0..6) | null,
          "hour":        int (0..23) | null,
          "count":       int,
        },
      }

    The 0..23 hour axis is in store-local time (driven by
    ``Store.timezone`` — UTC fallback when unset). Day-of-week
    is ISO (0=Monday … 6=Sunday) so the grid lines up with
    the ``store_hours`` schema.
    """
    store = db.get(Store, store_id)
    tz_name = (store.timezone or "UTC").strip() if store else "UTC"
    try:
        tz = ZoneInfo(tz_name)
    except ZoneInfoNotFoundError:
        tz = ZoneInfo("UTC")
    # Excluded statuses match the same convention used by
    # OwnerKpis: rejected / canceled transfers aren't real
    # activity for the heatmap.
    EXCLUDED = {"Rejected", "Canceled", "Cancelled"}
    rows = (
        db.query(Transfer.created_at, Transfer.status)
          .filter(
              Transfer.store_id == store_id,
              Transfer.created_at >= start,
              Transfer.created_at < end,
          )
          .all()
    )
    grid: list[list[int]] = [[0] * 24 for _ in range(7)]
    total = 0
    max_count = 0
    busiest_dow: int | None = None
    busiest_hour: int | None = None
    for created_at, status in rows:
        if created_at is None:
            continue
        if (status or "").strip() in EXCLUDED:
            continue
        # ``created_at`` is naive UTC by convention; attach
        # UTC tzinfo before converting to the store's local
        # zone.
        utc_aware = created_at.replace(tzinfo=ZoneInfo("UTC"))
        local = utc_aware.astimezone(tz)
        dow  = local.weekday()
        hour = local.hour
        grid[dow][hour] += 1
        total += 1
        cell = grid[dow][hour]
        if cell > max_count:
            max_count = cell
            busiest_dow = dow
            busiest_hour = hour
    return {
        "from_date":       start.date().isoformat(),
        "to_date":         end.date().isoformat(),
        "timezone":        tz_name,
        "total_transfers": total,
        "max_count":       max_count,
        "grid":            grid,
        "busiest": {
            "day_of_week": busiest_dow,
            "hour":        busiest_hour,
            "count":       max_count,
        },
    }
