"""Late-arrival derivation over ``TimeClockShift`` + ``TimeClockEntry``.

Pure functions — given a list of entries + the matching shifts in
the same window, return per-entry lateness in store-local minutes.
The controller layer reads through ``compute_lateness_map`` and
attaches the value to each ``TimeClockEntryRow``.

Matching rules
--------------

Multiple shifts per day per employee (split shifts: open + reopen
at lunch) are real, so we don't assume "one shift per
(employee, day)".  For each entry, we pair it with the shift
on the same date that has the closest ``start_time`` to the
entry's ``clock_in_at``.  Unmatched entries (admin back-fill
without a planned shift) get ``None``.

Lateness
--------

Computed as ``clock_in_local - shift.start_time`` in minutes.  A
zero or negative value means the cashier was on time or early.
Callers compare against ``Store.timeclock_late_minutes_threshold``
to decide whether the UI badge should fire.

Pure — no DB writes, no I/O.  The caller (controller layer) does
the SQLAlchemy queries.
"""
from __future__ import annotations

from datetime import date, datetime, time
from typing import Any, Iterable
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from api.Modules.TimeClock.Models import TimeClockEntry, TimeClockShift


def _to_store_local(
    when: datetime, store_timezone: str,
) -> datetime:
    """Convert a naive-UTC ``datetime`` (the storage convention for
    ``TimeClockEntry.clock_in_at``) to the store's local wall-clock.

    Empty / unknown timezones fall back to UTC — matches the
    rendering pattern used by ``formatTimestamp`` on the SPA.
    """
    if when.tzinfo is None:
        when = when.replace(tzinfo=ZoneInfo("UTC"))
    if not store_timezone:
        return when.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)
    try:
        tz = ZoneInfo(store_timezone)
    except ZoneInfoNotFoundError:
        return when.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)
    return when.astimezone(tz).replace(tzinfo=None)


def _match_shift(
    entry: TimeClockEntry,
    shifts_for_day: list[TimeClockShift],
    store_timezone: str,
) -> TimeClockShift | None:
    """Pick the shift whose start time is closest to ``entry.clock_in_at``.

    Multiple shifts per (employee, day) → match the closest one
    by absolute minute distance.  Returns None when ``shifts_for_day``
    is empty.
    """
    if not shifts_for_day:
        return None
    local_in = _to_store_local(
        entry.clock_in_at,  # type: ignore[arg-type]
        store_timezone,
    )
    entry_minutes = local_in.hour * 60 + local_in.minute
    best: TimeClockShift | None = None
    best_dist: int = 24 * 60 + 1
    for s in shifts_for_day:
        shift_minutes = s.start_time.hour * 60 + s.start_time.minute
        dist = abs(entry_minutes - shift_minutes)
        if dist < best_dist:
            best = s
            best_dist = dist
    return best


def _lateness_minutes(
    entry: TimeClockEntry,
    shift: TimeClockShift,
    store_timezone: str,
) -> int:
    """Minutes the entry's clock-in lags behind the shift's
    ``start_time``.  Can be negative (cashier punched in early).
    """
    local_in = _to_store_local(
        entry.clock_in_at,  # type: ignore[arg-type]
        store_timezone,
    )
    shift_dt = datetime.combine(
        local_in.date(),
        shift.start_time,  # type: ignore[arg-type]
    )
    delta = local_in - shift_dt
    # ``total_seconds`` divided by 60, rounded toward zero so
    # "59 seconds late" reads as 0 not 1.
    return int(delta.total_seconds() // 60)


def compute_lateness_map(
    entries: Iterable[TimeClockEntry],
    shifts: Iterable[TimeClockShift],
    *,
    store_timezone: str,
) -> dict[int, int]:
    """Return ``{entry_id: late_minutes}`` for every entry that
    has a matching shift on the same date+employee.  Entries
    without a planned shift are absent from the map (so callers
    can render "—" or omit the badge).
    """
    # Bucket shifts by (employee, date) for O(1) lookup.
    # SQLAlchemy 1.x types ``shift_date`` as ``Column[date]`` at
    # class-access time but the instance attribute is a plain
    # ``date`` at runtime — cast to keep the tuple key stable.
    by_key: dict[tuple[int, date], list[TimeClockShift]] = {}
    for s in shifts:
        shift_date_val: date = s.shift_date  # type: ignore[assignment]
        key = (int(s.store_employee_id), shift_date_val)
        by_key.setdefault(key, []).append(s)
    out: dict[int, int] = {}
    for e in entries:
        if e.clock_in_at is None:
            continue
        local_in = _to_store_local(
            e.clock_in_at,  # type: ignore[arg-type]
            store_timezone,
        )
        key = (int(e.store_employee_id), local_in.date())
        candidates = by_key.get(key, [])
        match = _match_shift(e, candidates, store_timezone)
        if match is None:
            continue
        out[int(e.id)] = _lateness_minutes(e, match, store_timezone)
    return out


def shifts_for_entries(
    db: Any,
    *,
    store_id: int,
    entries: Iterable[TimeClockEntry],
    store_timezone: str,
) -> list[TimeClockShift]:
    """Fetch the ``TimeClockShift`` rows that could possibly match
    the given entries, in one query.

    The date window is computed from the entries themselves so we
    only pull what the lateness join needs (no extra rows on
    either side of the period).  Returns an empty list when no
    entries are supplied.
    """
    dates: set[date] = set()
    employee_ids: set[int] = set()
    for e in entries:
        if e.clock_in_at is None:
            continue
        local_in = _to_store_local(
            e.clock_in_at,  # type: ignore[arg-type]
            store_timezone,
        )
        dates.add(local_in.date())
        employee_ids.add(int(e.store_employee_id))
    if not dates or not employee_ids:
        return []
    return list(
        db.query(TimeClockShift)
          .filter(
              TimeClockShift.store_id == store_id,
              TimeClockShift.shift_date.in_(dates),
              TimeClockShift.store_employee_id.in_(employee_ids),
          )
          .all()
    )
