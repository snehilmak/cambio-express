"""Unit tests for DailyBook.Services.locks (PR 81)."""
from datetime import date, datetime

from api.Modules.DailyBook.Models import DailyReport
from api.Modules.Tenancy.Models import Store
from tests._app import db, db_session


def _add_store(db, *, slug="locks-store"):
    s = Store(name=slug, slug=slug, plan="basic",
              email=f"{slug}@example.com")
    db.add(s); db.flush()
    return s


def _add_report(db, store_id, *, report_date,
                 locked_at=None):
    r = DailyReport(
        store_id=store_id,
        report_date=report_date,
        locked_at=locked_at,
    )
    db.add(r); db.flush()
    return r


# ── is_locked ────────────────────────────────────────────


def test_is_locked_returns_false_when_no_report():
    """Nothing to lock yet — returns False so write routes can
    proceed."""
    from tests._app import db
    from api.Modules.DailyBook.Services import is_daily_report_locked
    with db_session():
        db.session.query(DailyReport).delete()
        db.session.commit()
        s = _add_store(db.session, slug="locks-empty")
        assert is_daily_report_locked(
            db.session, s.id, date.today(),
        ) is False


def test_is_locked_returns_false_when_report_unlocked():
    """Row exists but locked_at is None → not locked."""
    from tests._app import db
    from api.Modules.DailyBook.Services import is_daily_report_locked
    with db_session():
        db.session.query(DailyReport).delete()
        db.session.commit()
        s = _add_store(db.session, slug="locks-unlocked")
        d = date(2026, 5, 1)
        _add_report(db.session, s.id, report_date=d, locked_at=None)
        assert is_daily_report_locked(db.session, s.id, d) is False


def test_is_locked_returns_true_when_report_locked():
    from tests._app import db
    from api.Modules.DailyBook.Services import is_daily_report_locked
    with db_session():
        db.session.query(DailyReport).delete()
        db.session.commit()
        s = _add_store(db.session, slug="locks-locked")
        d = date(2026, 5, 1)
        _add_report(
            db.session, s.id, report_date=d,
            locked_at=datetime.utcnow(),
        )
        assert is_daily_report_locked(db.session, s.id, d) is True


def test_is_locked_filters_by_store_and_date():
    """Locks on other stores or other dates don't leak."""
    from tests._app import db
    from api.Modules.DailyBook.Services import is_daily_report_locked
    with db_session():
        db.session.query(DailyReport).delete()
        db.session.commit()
        s1 = _add_store(db.session, slug="locks-isolation-1")
        s2 = _add_store(db.session, slug="locks-isolation-2")
        d1 = date(2026, 5, 1)
        d2 = date(2026, 5, 2)
        # Lock on store 1 / date 1.
        _add_report(
            db.session, s1.id, report_date=d1,
            locked_at=datetime.utcnow(),
        )
        # Same date, different store → not locked.
        assert is_daily_report_locked(db.session, s2.id, d1) is False
        # Same store, different date → not locked.
        assert is_daily_report_locked(db.session, s1.id, d2) is False


# ── legacy Flask wrapper ──────────────────────────────────


