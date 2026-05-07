"""Unit tests for the daily-report write-side lifecycle Service (PR 34)."""
from datetime import date, datetime


# ── ensure_daily_report ─────────────────────────────────────


def test_ensure_creates_when_missing(test_store_id):
    from app import app as flask_app, db, DailyReport
    from api.Modules.DailyBook.Services import ensure_daily_report
    today = date.today()
    with flask_app.app_context():
        # Sanity: nothing seeded yet
        assert DailyReport.query.filter_by(
            store_id=test_store_id, report_date=today,
        ).first() is None
        rpt = ensure_daily_report(db.session, test_store_id, today)
        assert rpt.id is not None
        assert rpt.store_id == test_store_id
        assert rpt.report_date == today
        assert rpt.taxable_sales == 0


def test_ensure_returns_existing(test_store_id):
    from app import app as flask_app, db, DailyReport
    from api.Modules.DailyBook.Services import ensure_daily_report
    today = date.today()
    with flask_app.app_context():
        seeded = DailyReport(
            store_id=test_store_id, report_date=today,
            taxable_sales=42.0,
        )
        db.session.add(seeded); db.session.commit()
        rpt = ensure_daily_report(db.session, test_store_id, today)
        assert rpt.id == seeded.id
        assert rpt.taxable_sales == 42.0


# ── lock_report ─────────────────────────────────────────────


def test_lock_report_sets_locked_at_and_locked_by(test_store_id, test_admin_id):
    from app import app as flask_app, db
    from api.Modules.DailyBook.Services import lock_report
    today = date.today()
    with flask_app.app_context():
        rpt = lock_report(
            db.session, test_store_id, today,
            locked_by_user_id=test_admin_id,
        )
        db.session.commit()
        assert rpt.locked_at is not None
        assert rpt.locked_by == test_admin_id


def test_lock_report_creates_empty_when_missing(test_store_id, test_admin_id):
    """Locking an empty day creates the DailyReport row first."""
    from app import app as flask_app, db, DailyReport
    from api.Modules.DailyBook.Services import lock_report
    today = date.today()
    with flask_app.app_context():
        assert DailyReport.query.filter_by(
            store_id=test_store_id, report_date=today,
        ).first() is None
        lock_report(
            db.session, test_store_id, today,
            locked_by_user_id=test_admin_id,
        )
        db.session.commit()
        rpt = DailyReport.query.filter_by(
            store_id=test_store_id, report_date=today,
        ).first()
        assert rpt is not None
        assert rpt.locked_at is not None


def test_lock_report_idempotent_when_already_locked(test_store_id, test_admin_id):
    """Re-locking shouldn't bump locked_at — that would look like a
    fresh action in the audit trail."""
    from app import app as flask_app, db
    from api.Modules.DailyBook.Services import lock_report
    today = date.today()
    with flask_app.app_context():
        first = lock_report(
            db.session, test_store_id, today,
            locked_by_user_id=test_admin_id,
        )
        db.session.commit()
        original_locked_at = first.locked_at
        second = lock_report(
            db.session, test_store_id, today,
            locked_by_user_id=test_admin_id,
        )
        db.session.commit()
        assert second.locked_at == original_locked_at


# ── unlock_report ───────────────────────────────────────────


def test_unlock_report_clears_lock_state(test_store_id, test_admin_id):
    from app import app as flask_app, db
    from api.Modules.DailyBook.Services import (
        lock_report, unlock_report,
    )
    today = date.today()
    with flask_app.app_context():
        lock_report(
            db.session, test_store_id, today,
            locked_by_user_id=test_admin_id,
        )
        db.session.commit()
        rpt = unlock_report(db.session, test_store_id, today)
        db.session.commit()
        assert rpt.locked_at is None
        assert rpt.locked_by is None


def test_unlock_report_returns_none_when_no_report(test_store_id):
    """No DailyReport row at all → returns None (no-op). Doesn't
    create an empty report (only locking does)."""
    from app import app as flask_app, db, DailyReport
    from api.Modules.DailyBook.Services import unlock_report
    today = date.today()
    with flask_app.app_context():
        assert unlock_report(db.session, test_store_id, today) is None
        # Still no row created
        assert DailyReport.query.filter_by(
            store_id=test_store_id, report_date=today,
        ).first() is None


def test_unlock_report_noop_when_not_locked(test_store_id):
    """Unlocking an unlocked report just returns the row unchanged."""
    from app import app as flask_app, db, DailyReport
    from api.Modules.DailyBook.Services import unlock_report
    today = date.today()
    with flask_app.app_context():
        seeded = DailyReport(
            store_id=test_store_id, report_date=today,
            taxable_sales=50.0,
        )
        db.session.add(seeded); db.session.commit()
        rpt = unlock_report(db.session, test_store_id, today)
        assert rpt is not None
        assert rpt.locked_at is None
