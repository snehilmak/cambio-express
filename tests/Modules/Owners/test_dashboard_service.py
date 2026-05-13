"""Unit tests for Owners.Services.dashboard (PR 61)."""
from datetime import date, timedelta

from api.Modules.DailyBook.Models import DailyReport
from api.Modules.Tenancy.Models import Store, StoreOwnerLink, User
from api.Modules.Transfers.Models import Transfer


# ── owner_period_window (pure date math) ───────────────────


def test_period_window_today_default():
    """Unrecognized period (or 'today') → single-day window."""
    from api.Modules.Owners.Services import owner_period_window
    today = date(2026, 5, 6)
    start, end, prev_start, prev_end, label = owner_period_window(
        "today", today,
    )
    assert start == today
    assert end == today
    assert prev_start == today - timedelta(days=1)
    assert prev_end == today - timedelta(days=1)
    assert label == "vs yesterday"


def test_period_window_today_handles_unknown_period():
    """Bogus period strings fall back to the 'today' branch."""
    from api.Modules.Owners.Services import owner_period_window
    today = date(2026, 5, 6)
    s, e, *_, label = owner_period_window("garbage", today)
    assert s == today and e == today
    assert label == "vs yesterday"


def test_period_window_month_starts_first_of_month():
    from api.Modules.Owners.Services import owner_period_window
    today = date(2026, 5, 6)
    start, end, prev_start, prev_end, label = owner_period_window(
        "month", today,
    )
    assert start == date(2026, 5, 1)
    assert end == today
    # prev window: same number of days as current ending day before start
    days = (end - start).days
    assert prev_end == date(2026, 4, 30)
    assert prev_start == prev_end - timedelta(days=days)
    assert label == "vs prior month"


def test_period_window_year_starts_jan_first():
    from api.Modules.Owners.Services import owner_period_window
    today = date(2026, 5, 6)
    start, end, prev_start, prev_end, label = owner_period_window(
        "year", today,
    )
    assert start == date(2026, 1, 1)
    assert end == today
    days = (end - start).days
    assert prev_end == date(2025, 12, 31)
    assert prev_start == prev_end - timedelta(days=days)
    assert label == "vs prior year"


# ── owner_store_ids ────────────────────────────────────────


def test_owner_store_ids_empty_for_user_with_no_links():
    from app import app as flask_app, db
    from api.Modules.Owners.Services import owner_store_ids
    with flask_app.app_context():
        u = User(
            username="lonely-owner@test.com",
            password_hash="x", role="owner",
            full_name="Lonely Owner", email="lonely-owner@test.com",
            store_id=1,
        )
        db.session.add(u); db.session.flush()
        assert owner_store_ids(db.session, u) == []


def test_owner_store_ids_returns_linked_stores():
    from app import app as flask_app, db
    from api.Modules.Owners.Services import owner_store_ids
    with flask_app.app_context():
        StoreOwnerLink.query.delete()
        db.session.commit()
        u = User(
            username="multi-owner@test.com",
            password_hash="x", role="owner",
            full_name="Multi Owner", email="multi-owner@test.com",
            store_id=1,
        )
        db.session.add(u); db.session.flush()
        s1 = Store(name="A", slug="store-a", plan="basic",
                   email="a@example.com")
        s2 = Store(name="B", slug="store-b", plan="basic",
                   email="b@example.com")
        db.session.add_all([s1, s2]); db.session.flush()
        db.session.add(StoreOwnerLink(owner_id=u.id, store_id=s1.id))
        db.session.add(StoreOwnerLink(owner_id=u.id, store_id=s2.id))
        db.session.flush()
        ids = owner_store_ids(db.session, u)
        assert sorted(ids) == sorted([s1.id, s2.id])


# ── owner_kpis ─────────────────────────────────────────────


def test_owner_kpis_empty_store_ids_returns_zeros():
    from app import app as flask_app, db
    from api.Modules.Owners.Services import owner_kpis
    with flask_app.app_context():
        result = owner_kpis(db.session, [], date.today(), date.today())
        assert result == (0, 0.0, 0.0)


def test_owner_kpis_aggregates_transfers_and_overshort():
    from app import app as flask_app, db
    from api.Modules.Owners.Services import owner_kpis
    with flask_app.app_context():
        Transfer.query.delete()
        DailyReport.query.delete()
        db.session.commit()
        s = Store(name="K", slug="store-k", plan="basic",
                  email="k@example.com")
        db.session.add(s); db.session.flush()
        today = date.today()
        # 2 transfers
        for amt in (100.0, 250.0):
            db.session.add(Transfer(
                store_id=s.id, send_date=today,
                company="Intermex", sender_name="x",
                send_amount=amt, fee=0.0, federal_tax=0.0,
                status="Sent",
            ))
        # 1 daily report with over_short=10
        db.session.add(DailyReport(
            store_id=s.id, report_date=today, over_short=10.0,
        ))
        db.session.flush()

        count, volume, os_total = owner_kpis(
            db.session, [s.id], today, today,
        )
        assert count == 2
        assert volume == 350.0
        assert os_total == 10.0


def test_owner_kpis_excludes_canceled_and_rejected():
    """Canceled/Rejected transfers must not inflate volume."""
    from app import app as flask_app, db
    from api.Modules.Owners.Services import owner_kpis
    with flask_app.app_context():
        Transfer.query.delete()
        DailyReport.query.delete()
        db.session.commit()
        s = Store(name="X", slug="store-x", plan="basic",
                  email="x@example.com")
        db.session.add(s); db.session.flush()
        today = date.today()
        # One sent + one canceled + one rejected → only 1 counted
        db.session.add(Transfer(
            store_id=s.id, send_date=today,
            company="Intermex", sender_name="x",
            send_amount=100.0, fee=0.0, federal_tax=0.0,
            status="Sent",
        ))
        db.session.add(Transfer(
            store_id=s.id, send_date=today,
            company="Intermex", sender_name="x",
            send_amount=200.0, fee=0.0, federal_tax=0.0,
            status="Canceled",
        ))
        db.session.add(Transfer(
            store_id=s.id, send_date=today,
            company="Intermex", sender_name="x",
            send_amount=300.0, fee=0.0, federal_tax=0.0,
            status="Rejected",
        ))
        db.session.flush()
        count, volume, _ = owner_kpis(
            db.session, [s.id], today, today,
        )
        assert count == 1
        assert volume == 100.0


def test_owner_kpis_filters_window():
    """Transfers outside the window don't count."""
    from app import app as flask_app, db
    from api.Modules.Owners.Services import owner_kpis
    with flask_app.app_context():
        Transfer.query.delete()
        db.session.commit()
        s = Store(name="W", slug="store-w", plan="basic",
                  email="w@example.com")
        db.session.add(s); db.session.flush()
        today = date.today()
        # Inside window
        db.session.add(Transfer(
            store_id=s.id, send_date=today,
            company="Intermex", sender_name="x",
            send_amount=100.0, fee=0.0, federal_tax=0.0,
            status="Sent",
        ))
        # Outside window (past)
        db.session.add(Transfer(
            store_id=s.id, send_date=today - timedelta(days=30),
            company="Intermex", sender_name="x",
            send_amount=999.0, fee=0.0, federal_tax=0.0,
            status="Sent",
        ))
        db.session.flush()
        count, volume, _ = owner_kpis(
            db.session, [s.id], today, today,
        )
        assert count == 1
        assert volume == 100.0


# ── legacy Flask wrappers ──────────────────────────────────


def test_legacy_period_window_delegates():
    from app import _owner_period_window as legacy
    today = date(2026, 5, 6)
    s, e, ps, pe, label = legacy("month", today)
    assert s == date(2026, 5, 1)
    assert label == "vs prior month"




def test_legacy_constants_re_exported():
    from app import _OWNER_TRANSFER_EXCLUDED
    assert "Canceled" in _OWNER_TRANSFER_EXCLUDED
    assert "Rejected" in _OWNER_TRANSFER_EXCLUDED
