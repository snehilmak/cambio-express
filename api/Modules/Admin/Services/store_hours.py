"""Store business-hours helpers.

The ``Store.store_hours`` column stores a JSON list of exactly
7 entries, one per ISO weekday (0=Monday … 6=Sunday). Each entry:

  {"day": int, "open": "HH:MM", "close": "HH:MM", "closed": bool}

NULL on the column means "not configured" — callers that need to
display the schedule (settings form, future "currently open"
indicator) substitute the ``DEFAULT_HOURS`` template below so the
operator never sees an empty 7-row form.

The "no transfers outside business hours" gating rule is a
separate backlog item; this module owns the read / validate /
write side only, plus the ``is_open_at`` predicate the
indicator / future-gate use to ask "is the store open right
now?".
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


# ── Constants ────────────────────────────────────────────────


DAY_LABELS: tuple[str, ...] = (
    "Monday", "Tuesday", "Wednesday", "Thursday",
    "Friday", "Saturday", "Sunday",
)

# Reasonable starter schedule for a remittance shop — closed on
# Sunday, open Mon-Sat 09:00-18:00. The settings page hydrates
# this when the column is NULL so the operator can save in one
# click without rebuilding the schedule from scratch.
DEFAULT_HOURS: list[dict[str, Any]] = [
    {"day": d, "open": "09:00", "close": "18:00", "closed": False}
    for d in range(6)
] + [
    {"day": 6, "open": "10:00", "close": "14:00", "closed": True},
]

_TIME_RE = re.compile(r"^[0-2]\d:[0-5]\d$")


# ── Public API ───────────────────────────────────────────────


def default_hours() -> list[dict[str, Any]]:
    """Fresh copy of ``DEFAULT_HOURS`` — never mutate the
    module-level template."""
    return [dict(entry) for entry in DEFAULT_HOURS]


def parse_stored_hours(value: Any) -> list[dict[str, Any]]:
    """Read-side coercion: pulls the JSON column out of the DB
    and returns a canonical list-of-7. Falls back to defaults on
    NULL / malformed values so the settings UI always has a
    complete schedule to render. Never raises — the only caller
    is the read-side adapter."""
    if not isinstance(value, list) or len(value) != 7:
        return default_hours()
    out: list[dict[str, Any]] = []
    for d in range(7):
        entry = _coerce_entry(value[d], d)
        out.append(entry)
    return out


def validate_hours_payload(payload: Any) -> list[dict[str, Any]]:
    """Write-side validation: raises ``ValueError`` on any shape
    drift. Returns the canonical normalized form ready to assign
    to ``Store.store_hours``. Callers commit."""
    if not isinstance(payload, list):
        raise ValueError("store_hours must be a list of 7 entries.")
    if len(payload) != 7:
        raise ValueError(
            f"store_hours must have exactly 7 entries (got {len(payload)}).",
        )
    seen_days: set[int] = set()
    out: list[dict[str, Any]] = []
    for i, raw in enumerate(payload):
        if not isinstance(raw, dict):
            raise ValueError(f"Entry {i}: expected an object.")
        day = raw.get("day")
        if not isinstance(day, int) or day < 0 or day > 6:
            raise ValueError(
                f"Entry {i}: 'day' must be 0..6 (0=Monday, 6=Sunday).",
            )
        if day in seen_days:
            raise ValueError(f"Entry {i}: duplicate day {day}.")
        seen_days.add(day)
        open_str  = _coerce_time(raw.get("open"), i, "open")
        close_str = _coerce_time(raw.get("close"), i, "close")
        closed = bool(raw.get("closed", False))
        # Only enforce open < close when the day is marked open —
        # a "closed" day can hold any sentinel time pair without
        # tripping the validator.
        if not closed and open_str >= close_str:
            raise ValueError(
                f"Entry {i}: 'open' ({open_str}) must come before "
                f"'close' ({close_str}).",
            )
        out.append({
            "day": day, "open": open_str, "close": close_str,
            "closed": closed,
        })
    # Order by day for stable storage / display.
    out.sort(key=lambda e: e["day"])
    return out


def store_now(timezone: str | None) -> datetime:
    """Current wall-clock datetime in the given IANA timezone
    (or UTC if empty / unknown). Naive — strips tzinfo so it
    composes with ``is_open_at`` cleanly. Bad tz strings degrade
    to UTC silently; the operator can fix the value in Settings."""
    tz_name = (timezone or "").strip() or "UTC"
    try:
        tz = ZoneInfo(tz_name)
    except ZoneInfoNotFoundError:
        tz = ZoneInfo("UTC")
    return datetime.now(tz=tz).replace(tzinfo=None)


def is_open_at(stored_hours: Any, when: datetime) -> bool:
    """Return True if ``when`` falls inside the store's open
    window for that weekday. Callers pass the raw column value
    — we run it through ``parse_stored_hours`` so a NULL /
    malformed column treats every day as open 09:00-18:00 (the
    default schedule), which is the safest default for a
    soft-warning indicator. ``when`` is expected to already be
    in the store's local timezone.
    """
    hours = parse_stored_hours(stored_hours)
    # ``date.weekday()`` returns 0=Monday … 6=Sunday — same
    # convention as our schema.
    entry = hours[when.weekday()]
    if entry.get("closed"):
        return False
    open_min  = _minute_of_day(entry.get("open"))
    close_min = _minute_of_day(entry.get("close"))
    now_min   = when.hour * 60 + when.minute
    if open_min is None or close_min is None:
        # Defensive — ``parse_stored_hours`` already substituted
        # defaults so this branch only fires for genuinely
        # broken inputs the read-side healer couldn't fix.
        return False
    return open_min <= now_min < close_min


def _minute_of_day(value: Any) -> int | None:
    if not isinstance(value, str) or not _TIME_RE.match(value):
        return None
    hh, mm = value.split(":", 1)
    hour = int(hh)
    if hour > 23:
        return None
    return hour * 60 + int(mm)


# ── Internal helpers ─────────────────────────────────────────


def _coerce_entry(raw: Any, expected_day: int) -> dict[str, Any]:
    """Best-effort read-side coercion — fills sensible defaults
    if the stored value is missing or malformed for one day."""
    if not isinstance(raw, dict):
        return {
            "day": expected_day, "open": "09:00", "close": "18:00",
            "closed": False,
        }
    return {
        "day": expected_day,
        "open":   _safe_time(raw.get("open"),  "09:00"),
        "close":  _safe_time(raw.get("close"), "18:00"),
        "closed": bool(raw.get("closed", False)),
    }


def _coerce_time(raw: Any, idx: int, field: str) -> str:
    if not isinstance(raw, str) or not _TIME_RE.match(raw):
        raise ValueError(
            f"Entry {idx}: {field!r} must be a 'HH:MM' 24h string.",
        )
    hh, mm = raw.split(":")
    if int(hh) > 23:
        raise ValueError(
            f"Entry {idx}: {field!r} hour must be 00..23 (got {hh}).",
        )
    return raw


def _safe_time(raw: Any, fallback: str) -> str:
    if isinstance(raw, str) and _TIME_RE.match(raw):
        hh = int(raw.split(":", 1)[0])
        if 0 <= hh <= 23:
            return raw
    return fallback
