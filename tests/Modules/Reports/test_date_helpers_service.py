"""Unit tests for Reports.Services.date_helpers (PR 83)."""
from datetime import date, datetime


# ── day_start ────────────────────────────────────────────


def test_day_start_returns_midnight_naive_datetime():
    from api.Modules.Reports.Services import day_start
    result = day_start(date(2026, 5, 15))
    assert result == datetime(2026, 5, 15, 0, 0, 0)
    # Naive — no tzinfo.
    assert result.tzinfo is None


def test_day_start_works_at_year_boundary():
    from api.Modules.Reports.Services import day_start
    result = day_start(date(2026, 1, 1))
    assert result == datetime(2026, 1, 1, 0, 0, 0)


def test_day_start_works_at_month_end():
    from api.Modules.Reports.Services import day_start
    result = day_start(date(2026, 2, 28))
    assert result == datetime(2026, 2, 28, 0, 0, 0)


# ── day_end ──────────────────────────────────────────────


def test_day_end_returns_last_second_naive_datetime():
    from api.Modules.Reports.Services import day_end
    result = day_end(date(2026, 5, 15))
    assert result == datetime(2026, 5, 15, 23, 59, 59)
    assert result.tzinfo is None


def test_day_end_works_at_leap_day():
    from api.Modules.Reports.Services import day_end
    result = day_end(date(2024, 2, 29))
    assert result == datetime(2024, 2, 29, 23, 59, 59)


def test_day_end_works_at_year_boundary():
    from api.Modules.Reports.Services import day_end
    result = day_end(date(2025, 12, 31))
    assert result == datetime(2025, 12, 31, 23, 59, 59)


# ── relationship between start/end ───────────────────────


def test_day_start_before_day_end_for_same_date():
    from api.Modules.Reports.Services import day_end, day_start
    d = date(2026, 6, 15)
    assert day_start(d) < day_end(d)
    # The window is one day minus one second.
    delta = day_end(d) - day_start(d)
    assert delta.days == 0
    assert delta.seconds == 23 * 3600 + 59 * 60 + 59


# ── legacy Flask wrappers ────────────────────────────────


def test_legacy_day_start_delegates():
    from app import _day_start as legacy
    assert legacy(date(2026, 5, 15)) == datetime(2026, 5, 15)


def test_legacy_day_end_delegates():
    from app import _day_end as legacy
    assert legacy(date(2026, 5, 15)) == datetime(
        2026, 5, 15, 23, 59, 59,
    )


def test_legacy_re_exports_are_same_callable():
    """app._day_start / _day_end are the same function objects as
    the Service exports — re-exported, not wrapped."""
    from app import _day_end as legacy_end, _day_start as legacy_start
    from api.Modules.Reports.Services import (
        day_end, day_start,
    )
    assert legacy_start is day_start
    assert legacy_end is day_end
