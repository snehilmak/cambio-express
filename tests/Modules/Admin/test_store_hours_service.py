"""Unit tests for ``Admin.Services.store_hours``.

These exercise the validation + read-side coercion in isolation
— no HTTP layer involved. The controller-level happy path is
covered by ``test_admin_controllers.py``.
"""
from datetime import datetime

import pytest

from api.Modules.Admin.Services.store_hours import (
    DEFAULT_HOURS,
    default_hours,
    is_open_at,
    parse_stored_hours,
    validate_hours_payload,
)


def _full_week(closed=()) -> list[dict]:
    return [
        {
            "day": d, "open": "09:00", "close": "18:00",
            "closed": d in closed,
        }
        for d in range(7)
    ]


# ── default_hours ───────────────────────────────────────────


def test_default_hours_returns_fresh_copy():
    """Mutating the returned list must NOT mutate the module-
    level template — otherwise a single bad write would poison
    every subsequent default-hours read."""
    a = default_hours()
    a[0]["open"] = "X"
    b = default_hours()
    assert b[0]["open"] == "09:00"
    # Template untouched too.
    assert DEFAULT_HOURS[0]["open"] == "09:00"


def test_default_hours_covers_all_7_days():
    days = {row["day"] for row in default_hours()}
    assert days == set(range(7))


# ── parse_stored_hours ──────────────────────────────────────


def test_parse_stored_hours_null_falls_back_to_default():
    """NULL on the column → defaults, so the settings UI has
    something to render."""
    assert len(parse_stored_hours(None)) == 7


def test_parse_stored_hours_wrong_length_falls_back():
    """A row with 3 entries is corrupt — same as NULL, render
    defaults rather than crashing the settings page."""
    assert len(parse_stored_hours([{"day": 0}])) == 7


def test_parse_stored_hours_preserves_valid_input():
    payload = _full_week(closed=(6,))
    payload[0]["open"] = "07:00"
    out = parse_stored_hours(payload)
    assert out[0]["open"] == "07:00"
    assert out[6]["closed"] is True


def test_parse_stored_hours_substitutes_per_row_defaults():
    """A single malformed row inside an otherwise-good list gets
    healed without taking down the whole schedule."""
    payload = _full_week()
    payload[2] = "not a dict"  # type: ignore[list-item]
    out = parse_stored_hours(payload)
    assert out[2] == {
        "day": 2, "open": "09:00", "close": "18:00", "closed": False,
    }


# ── validate_hours_payload ──────────────────────────────────


def test_validate_hours_payload_happy_path():
    out = validate_hours_payload(_full_week())
    assert len(out) == 7
    # Always sorted by day for stable storage.
    assert [row["day"] for row in out] == list(range(7))


def test_validate_hours_payload_rejects_non_list():
    with pytest.raises(ValueError, match="list of 7"):
        validate_hours_payload({"day": 0})


def test_validate_hours_payload_rejects_wrong_length():
    with pytest.raises(ValueError, match="exactly 7"):
        validate_hours_payload(_full_week()[:5])


def test_validate_hours_payload_rejects_day_out_of_range():
    payload = _full_week()
    payload[0]["day"] = 9
    with pytest.raises(ValueError, match="'day' must be 0..6"):
        validate_hours_payload(payload)


def test_validate_hours_payload_rejects_duplicate_day():
    payload = _full_week()
    payload[1]["day"] = 0
    with pytest.raises(ValueError, match="duplicate day"):
        validate_hours_payload(payload)


def test_validate_hours_payload_rejects_open_after_close():
    payload = _full_week()
    payload[0]["open"]  = "20:00"
    payload[0]["close"] = "08:00"
    with pytest.raises(ValueError, match="must come before"):
        validate_hours_payload(payload)


def test_validate_hours_payload_allows_inverted_times_when_closed():
    """The open<close check is skipped for closed days — the
    times become sentinel values the gating layer ignores."""
    payload = _full_week(closed=(0,))
    payload[0]["open"]  = "23:00"
    payload[0]["close"] = "01:00"
    out = validate_hours_payload(payload)
    assert out[0]["closed"] is True


def test_validate_hours_payload_rejects_single_digit_hour():
    """Pydantic max_length=5 lets "9:00" through (it's 4 chars);
    the service-layer regex is what actually rejects it."""
    payload = _full_week()
    payload[0]["open"] = "9:00"
    with pytest.raises(ValueError, match="HH:MM"):
        validate_hours_payload(payload)


def test_validate_hours_payload_rejects_hour_over_23():
    payload = _full_week()
    payload[0]["open"] = "25:00"
    with pytest.raises(ValueError, match="HH:MM|00..23"):
        validate_hours_payload(payload)


def test_validate_hours_payload_normalizes_sort_order():
    payload = list(reversed(_full_week()))
    out = validate_hours_payload(payload)
    assert [row["day"] for row in out] == list(range(7))


# ── is_open_at ──────────────────────────────────────────────


def _mon(hour: int, minute: int = 0) -> datetime:
    # 2026-05-18 is a Monday — anchor every test on a known
    # weekday so the day-of-week math is deterministic.
    return datetime(2026, 5, 18, hour, minute)


def _sun(hour: int = 12) -> datetime:
    # 2026-05-17 is a Sunday.
    return datetime(2026, 5, 17, hour)


def test_is_open_at_inside_window():
    """Mid-day on a configured open day returns True."""
    assert is_open_at(_full_week(), _mon(12, 0)) is True


def test_is_open_at_before_open_time():
    """Right before the open boundary returns False."""
    assert is_open_at(_full_week(), _mon(8, 59)) is False


def test_is_open_at_at_open_boundary():
    """Open boundary is inclusive — the store opens AT 09:00."""
    assert is_open_at(_full_week(), _mon(9, 0)) is True


def test_is_open_at_at_close_boundary():
    """Close boundary is exclusive — "closes at 18:00" means
    18:00 itself counts as closed."""
    assert is_open_at(_full_week(), _mon(18, 0)) is False


def test_is_open_at_after_close():
    assert is_open_at(_full_week(), _mon(20, 30)) is False


def test_is_open_at_closed_day():
    """``closed=True`` short-circuits regardless of the time
    pair on the entry."""
    assert is_open_at(_full_week(closed=(0,)), _mon(12, 0)) is False


def test_is_open_at_sunday_default_closed():
    """The default schedule closes Sunday — every hour returns
    False there."""
    for hour in (0, 9, 12, 17, 23):
        assert is_open_at(DEFAULT_HOURS, _sun(hour)) is False


def test_is_open_at_null_falls_back_to_defaults():
    """A NULL ``stored_hours`` is healed through
    ``parse_stored_hours`` — Monday open at noon is True."""
    assert is_open_at(None, _mon(12, 0)) is True


def test_is_open_at_uses_weekday_index_correctly():
    """Tuesday-only schedule (everything else closed) opens
    Tuesday but closes Monday + Wednesday — pins the
    ``date.weekday()`` ↔ ``day`` mapping."""
    hours = _full_week(closed=(0, 2, 3, 4, 5, 6))
    # 2026-05-19 is a Tuesday.
    tuesday_noon = datetime(2026, 5, 19, 12)
    monday_noon  = _mon(12, 0)
    wed_noon     = datetime(2026, 5, 20, 12)
    assert is_open_at(hours, tuesday_noon) is True
    assert is_open_at(hours, monday_noon)  is False
    assert is_open_at(hours, wed_noon)     is False
