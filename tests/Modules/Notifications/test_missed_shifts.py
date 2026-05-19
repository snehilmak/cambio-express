"""Tests for the missed-shift digest service.

Three layers:

  - Pure-function tests for ``find_missed_shifts`` — drive the
    "shift without a matching entry" logic against an in-memory
    DB seed.
  - End-to-end ``run`` orchestrator — assert that the SMTP send
    fires once per eligible recipient, that stores with no
    missed shifts don't trigger any mail, and that the
    ``missed_shifts_sent_for`` dedup marker is set.
  - Recipient filter — confirms the same gates as the daily
    summary apply (active + opted-in + non-bounced).
"""
from datetime import date, datetime, time, timedelta
from unittest.mock import patch

from tests._app import db, db_session


def _seed_employee(store_id, *, name="Maria"):
    from api.Modules.Tenancy.Models import StoreEmployee
    e = StoreEmployee(store_id=store_id, name=name, is_active=True)
    db.session.add(e); db.session.commit()
    return e.id


def _seed_shift(store_id, employee_id, on_date, *, start=time(9, 0), end=time(17, 0)):
    from api.Modules.TimeClock.Models import TimeClockShift
    s = TimeClockShift(
        store_id=store_id, store_employee_id=employee_id,
        shift_date=on_date, start_time=start, end_time=end,
    )
    db.session.add(s); db.session.commit()
    return s.id


def _seed_entry(store_id, employee_id, *, clock_in_at: datetime):
    from api.Modules.TimeClock.Models import TimeClockEntry
    e = TimeClockEntry(
        store_id=store_id, store_employee_id=employee_id,
        clock_in_at=clock_in_at,
    )
    db.session.add(e); db.session.commit()
    return e.id


# ── Pure-function tests ────────────────────────────────────


def test_find_missed_shifts_returns_unpunched_shifts(test_store_id):
    """A shift on ``on_date`` with no entry for the same
    employee on the same date is flagged."""
    from api.Modules.Notifications.Services.missed_shifts import (
        find_missed_shifts,
    )
    with db_session():
        emp_a = _seed_employee(test_store_id, name="Maria")
        emp_b = _seed_employee(test_store_id, name="Juan")
        on_date = date(2026, 5, 18)
        # Maria has a shift but DIDN'T punch in — missed.
        _seed_shift(test_store_id, emp_a, on_date)
        # Juan has a shift AND punched in — not missed.
        _seed_shift(test_store_id, emp_b, on_date)
        _seed_entry(
            test_store_id, emp_b,
            clock_in_at=datetime(2026, 5, 18, 9, 15),
        )

        missed = find_missed_shifts(
            db.session, store_id=test_store_id, on_date=on_date,
        )
    employee_ids = [int(s.store_employee_id) for s in missed]
    assert employee_ids == [emp_a]


def test_find_missed_shifts_late_arrival_is_not_missed(test_store_id):
    """A cashier who clocked in but at the wrong time still
    counts as "showed up" — phase 1's late-arrival badge handles
    that case; the digest is for the NO-show case."""
    from api.Modules.Notifications.Services.missed_shifts import (
        find_missed_shifts,
    )
    with db_session():
        emp = _seed_employee(test_store_id, name="Maria")
        on_date = date(2026, 5, 18)
        _seed_shift(test_store_id, emp, on_date, start=time(9, 0))
        # Clocked in at 13:00 — three hours late but punched in.
        _seed_entry(
            test_store_id, emp,
            clock_in_at=datetime(2026, 5, 18, 13, 0),
        )

        missed = find_missed_shifts(
            db.session, store_id=test_store_id, on_date=on_date,
        )
    assert missed == []


def test_find_missed_shifts_isolates_dates(test_store_id):
    """An entry on a different day doesn't satisfy today's shift."""
    from api.Modules.Notifications.Services.missed_shifts import (
        find_missed_shifts,
    )
    with db_session():
        emp = _seed_employee(test_store_id, name="Maria")
        _seed_shift(test_store_id, emp, date(2026, 5, 18))
        # Clocked in the day BEFORE — doesn't cover Monday's shift.
        _seed_entry(
            test_store_id, emp,
            clock_in_at=datetime(2026, 5, 17, 9, 15),
        )

        missed = find_missed_shifts(
            db.session, store_id=test_store_id,
            on_date=date(2026, 5, 18),
        )
    assert len(missed) == 1


def test_find_missed_shifts_empty_when_no_shifts(test_store_id):
    """No planned shifts → no misses, even when entries exist on
    the date."""
    from api.Modules.Notifications.Services.missed_shifts import (
        find_missed_shifts,
    )
    with db_session():
        emp = _seed_employee(test_store_id)
        _seed_entry(
            test_store_id, emp,
            clock_in_at=datetime(2026, 5, 18, 9, 15),
        )

        missed = find_missed_shifts(
            db.session, store_id=test_store_id,
            on_date=date(2026, 5, 18),
        )
    assert missed == []


# ── Orchestrator + dedup ──────────────────────────────────


def _set_admin_email(store_id, email="admin@test.com"):
    """The conftest seed leaves ``User.email`` empty.  Set it so
    the eligibility predicate (email != "") matches."""
    from api.Modules.Tenancy.Models import User
    admin = (
        db.session.query(User)
          .filter_by(store_id=store_id, role="admin")
          .first()
    )
    setattr(admin, "email", email)
    db.session.commit()


def test_run_sends_to_each_eligible_recipient(test_store_id):
    """Per recipient: one email send.  The push side is
    best-effort and may no-op when VAPID isn't configured."""
    from api.Modules.Notifications.Services import missed_shifts as svc
    with db_session():
        emp = _seed_employee(test_store_id, name="Maria")
        _seed_shift(test_store_id, emp, date(2026, 5, 18))
        _set_admin_email(test_store_id)

    with patch("api.Modules.Notifications.Services.smtp.send_email") as send:
        with db_session():
            n = svc.run(db.session, on_date=date(2026, 5, 18))
        assert n == 1
        assert send.call_count == 1


def test_run_stamps_sent_marker_and_skips_redundant_runs(test_store_id):
    from api.Modules.Notifications.Services import missed_shifts as svc
    from api.Modules.Tenancy.Models import Store
    with db_session():
        emp = _seed_employee(test_store_id, name="Maria")
        _seed_shift(test_store_id, emp, date(2026, 5, 18))
        _set_admin_email(test_store_id)

    with patch("api.Modules.Notifications.Services.smtp.send_email") as send:
        with db_session():
            svc.run(db.session, on_date=date(2026, 5, 18))
        first_call_count = send.call_count

        # Second run for the same date — fully no-ops because the
        # marker is set.
        with db_session():
            svc.run(db.session, on_date=date(2026, 5, 18))
        assert send.call_count == first_call_count

    with db_session():
        store = db.session.get(Store, test_store_id)
        assert store.missed_shifts_sent_for == date(2026, 5, 18)


def test_run_skips_stores_with_no_misses(test_store_id):
    """A store with shifts that were all punched gets no email
    but still gets the marker stamped so subsequent runs don't
    re-query."""
    from api.Modules.Notifications.Services import missed_shifts as svc
    from api.Modules.Tenancy.Models import Store
    with db_session():
        emp = _seed_employee(test_store_id, name="Maria")
        _seed_shift(test_store_id, emp, date(2026, 5, 18))
        _seed_entry(
            test_store_id, emp,
            clock_in_at=datetime(2026, 5, 18, 9, 0),
        )

    with patch("api.Modules.Notifications.Services.smtp.send_email") as send:
        with db_session():
            n = svc.run(db.session, on_date=date(2026, 5, 18))
        assert n == 0
        assert send.call_count == 0

    with db_session():
        store = db.session.get(Store, test_store_id)
        assert store.missed_shifts_sent_for == date(2026, 5, 18)


def test_eligible_recipients_excludes_opted_out_users(test_store_id):
    """A user with ``notify_daily_summary=False`` doesn't get the
    missed-shift digest — phase 1 reuses the same toggle."""
    from api.Modules.Notifications.Services.missed_shifts import (
        eligible_recipients,
    )
    from api.Modules.Tenancy.Models import Store, User
    with db_session():
        # Flip the test admin's daily-summary opt-out.
        admin = (
            db.session.query(User)
              .filter_by(store_id=test_store_id, role="admin")
              .first()
        )
        setattr(admin, "notify_daily_summary", False)
        # Need an email for the recipient predicate to consider them.
        setattr(admin, "email", "admin@test.com")
        db.session.commit()
        store = db.session.get(Store, test_store_id)
        result = eligible_recipients(db.session, store)
    assert result == []
