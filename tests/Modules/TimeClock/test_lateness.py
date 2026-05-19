"""Tests for the late-arrival derivation.

Two layers:

  - Pure-function tests for ``compute_lateness_map`` — drive the
    matching + minute math without DB scaffolding.
  - Integration tests against ``GET /api/v2/admin/timeclock`` that
    seed a shift + a clock-in and assert the payload's
    ``late_minutes`` field reflects the lag.

Tenancy + auth coverage lives in
``tests/Modules/TimeClock/test_timeclock_endpoint.py``; this file
focuses on the lateness join specifically.
"""
from datetime import date, datetime, time

from tests._app import db, db_session


def _login_admin(client_, store_id):
    return client_.post(
        "/api/v2/auth/login",
        json={
            "username": "admin@test.com",
            "password": "testpass123!",
            "store_id": store_id,
        },
    ).get_json()["access_token"]


def _seed_employee(store_id, *, name="Maria"):
    from api.Modules.Tenancy.Models import StoreEmployee
    e = StoreEmployee(store_id=store_id, name=name, is_active=True)
    db.session.add(e); db.session.commit()
    return e.id


# ── Pure-function tests ────────────────────────────────────


def test_compute_lateness_map_matches_same_day_closest_shift():
    from api.Modules.TimeClock.Models import TimeClockEntry, TimeClockShift
    from api.Modules.TimeClock.Services.lateness import compute_lateness_map

    # Two shifts on Monday for the same employee — split shift.
    shift_morning = TimeClockShift(
        id=1, store_id=1, store_employee_id=42,
        shift_date=date(2026, 5, 18),
        start_time=time(9, 0), end_time=time(12, 0),
    )
    shift_afternoon = TimeClockShift(
        id=2, store_id=1, store_employee_id=42,
        shift_date=date(2026, 5, 18),
        start_time=time(13, 0), end_time=time(17, 0),
    )
    # Entry punched in at 13:07 — should match the afternoon shift
    # and report 7 minutes late.
    entry = TimeClockEntry(
        id=10, store_id=1, store_employee_id=42,
        clock_in_at=datetime(2026, 5, 18, 13, 7),
    )

    out = compute_lateness_map(
        [entry], [shift_morning, shift_afternoon], store_timezone="",
    )
    assert out == {10: 7}


def test_compute_lateness_map_negative_when_early():
    from api.Modules.TimeClock.Models import TimeClockEntry, TimeClockShift
    from api.Modules.TimeClock.Services.lateness import compute_lateness_map

    shift = TimeClockShift(
        id=1, store_id=1, store_employee_id=42,
        shift_date=date(2026, 5, 18),
        start_time=time(9, 0), end_time=time(17, 0),
    )
    entry = TimeClockEntry(
        id=10, store_id=1, store_employee_id=42,
        clock_in_at=datetime(2026, 5, 18, 8, 50),  # 10 min early
    )
    out = compute_lateness_map([entry], [shift], store_timezone="")
    assert out == {10: -10}


def test_compute_lateness_map_skips_entries_without_planned_shift():
    from api.Modules.TimeClock.Models import TimeClockEntry, TimeClockShift
    from api.Modules.TimeClock.Services.lateness import compute_lateness_map

    # Shift for employee 42, but entry is for employee 99 — no match.
    shift = TimeClockShift(
        id=1, store_id=1, store_employee_id=42,
        shift_date=date(2026, 5, 18),
        start_time=time(9, 0), end_time=time(17, 0),
    )
    entry = TimeClockEntry(
        id=10, store_id=1, store_employee_id=99,
        clock_in_at=datetime(2026, 5, 18, 9, 5),
    )
    out = compute_lateness_map([entry], [shift], store_timezone="")
    assert out == {}


def test_compute_lateness_map_respects_store_timezone():
    """A New York store sees 13:30 UTC as 09:30 EDT — a 9am shift
    is late by 30 minutes in the store's local time."""
    from api.Modules.TimeClock.Models import TimeClockEntry, TimeClockShift
    from api.Modules.TimeClock.Services.lateness import compute_lateness_map

    shift = TimeClockShift(
        id=1, store_id=1, store_employee_id=42,
        shift_date=date(2026, 5, 18),  # store-local date
        start_time=time(9, 0), end_time=time(17, 0),
    )
    entry = TimeClockEntry(
        id=10, store_id=1, store_employee_id=42,
        clock_in_at=datetime(2026, 5, 18, 13, 30),  # 09:30 EDT
    )
    out = compute_lateness_map(
        [entry], [shift], store_timezone="America/New_York",
    )
    assert out == {10: 30}


# ── Integration via /api/v2/admin/timeclock ────────────────


def test_admin_entries_includes_late_minutes(client, test_store_id):
    """End-to-end: create a shift, post a clock-in, fetch payroll
    history, expect the row to carry ``late_minutes``."""
    from api.Modules.TimeClock.Models import (
        TimeClockEntry,
        TimeClockShift,
    )
    with db_session():
        emp_id = _seed_employee(test_store_id)
        shift = TimeClockShift(
            store_id=test_store_id, store_employee_id=emp_id,
            shift_date=date(2026, 5, 18),
            start_time=time(9, 0), end_time=time(17, 0),
        )
        entry = TimeClockEntry(
            store_id=test_store_id, store_employee_id=emp_id,
            clock_in_at=datetime(2026, 5, 18, 9, 8),  # 8 min late
        )
        db.session.add(shift); db.session.add(entry); db.session.commit()
        entry_id = entry.id

    token = _login_admin(client, test_store_id)
    body = client.get(
        "/api/v2/admin/timeclock?from=2026-05-18&to=2026-05-19",
        headers={"Authorization": f"Bearer {token}"},
    ).get_json()
    matching = [r for r in body["rows"] if r["id"] == entry_id]
    assert len(matching) == 1
    assert matching[0]["late_minutes"] == 8
    # Default threshold is 5, so this 8-min late punch crosses it.
    assert body["late_threshold_minutes"] == 5


def test_admin_entries_null_late_minutes_when_no_planned_shift(
    client, test_store_id,
):
    """An entry without a matching ``TimeClockShift`` row gets
    ``late_minutes=None`` (no badge)."""
    from api.Modules.TimeClock.Models import TimeClockEntry
    with db_session():
        emp_id = _seed_employee(test_store_id)
        entry = TimeClockEntry(
            store_id=test_store_id, store_employee_id=emp_id,
            clock_in_at=datetime(2026, 5, 18, 9, 8),
        )
        db.session.add(entry); db.session.commit()
        entry_id = entry.id

    token = _login_admin(client, test_store_id)
    body = client.get(
        "/api/v2/admin/timeclock?from=2026-05-18&to=2026-05-19",
        headers={"Authorization": f"Bearer {token}"},
    ).get_json()
    matching = [r for r in body["rows"] if r["id"] == entry_id]
    assert len(matching) == 1
    assert matching[0]["late_minutes"] is None


def test_admin_entries_returns_store_late_threshold(
    client, test_store_id,
):
    """The list endpoint should round-trip the store's configured
    threshold so the SPA can decide when to render the pill."""
    from api.Modules.Tenancy.Models import Store
    with db_session():
        store = db.session.get(Store, test_store_id)
        setattr(store, "timeclock_late_minutes_threshold", 12)
        db.session.commit()
    token = _login_admin(client, test_store_id)
    body = client.get(
        "/api/v2/admin/timeclock?from=2026-05-18&to=2026-05-19",
        headers={"Authorization": f"Bearer {token}"},
    ).get_json()
    assert body["late_threshold_minutes"] == 12
