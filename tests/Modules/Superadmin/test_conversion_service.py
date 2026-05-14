"""Unit tests for SA conversion / trial-timing services (PR 99)."""
from datetime import date, datetime, timedelta

from api.Modules.Tenancy.Models import Store
from tests._app import db


def _add_store(db, *, slug, plan="trial",
               created_at=None, trial_ends_at=None):
    s = Store(name=slug, slug=slug, plan=plan,
              email=f"{slug}@example.com",
              created_at=created_at or datetime.utcnow(),
              trial_ends_at=trial_ends_at)
    db.add(s); db.flush()
    return s


# ── conversion_rate ──────────────────────────────────────


def test_conversion_rate_returns_three_buckets():
    """Always returns Paid / Trial / Inactive rows in fixed order
    so the template can render the same 3 cards."""
    from tests._app import app as flask_app, db
    from api.Modules.Superadmin.Services import conversion_rate
    with flask_app.app_context():
        db.session.query(Store).delete()
        db.session.commit()
        rows, _ = conversion_rate(
            db.session, date(2026, 5, 1), date(2026, 5, 31),
        )
        assert [r["label"] for r in rows] == ["Paid", "Trial", "Inactive"]


def test_conversion_rate_counts_per_plan():
    from tests._app import app as flask_app, db
    from api.Modules.Superadmin.Services import conversion_rate
    with flask_app.app_context():
        db.session.query(Store).delete()
        db.session.commit()
        _add_store(db.session, slug="cr-paid",   plan="basic",
                   created_at=datetime(2026, 5, 5))
        _add_store(db.session, slug="cr-trial",  plan="trial",
                   created_at=datetime(2026, 5, 6))
        _add_store(db.session, slug="cr-trial2", plan="trial",
                   created_at=datetime(2026, 5, 7))
        _add_store(db.session, slug="cr-inact",  plan="inactive",
                   created_at=datetime(2026, 5, 8))
        rows, totals = conversion_rate(
            db.session, date(2026, 5, 1), date(2026, 5, 31),
        )
        by_label = {r["label"]: r["count"] for r in rows}
        assert by_label == {"Paid": 1, "Trial": 2, "Inactive": 1}
        assert totals["total"] == 4
        assert totals["paid"]  == 1
        assert totals["rate"]  == 25.0


def test_conversion_rate_zero_total_returns_zero_rate():
    """No signups → rate = 0 (no divide-by-zero)."""
    from tests._app import app as flask_app, db
    from api.Modules.Superadmin.Services import conversion_rate
    with flask_app.app_context():
        db.session.query(Store).delete()
        db.session.commit()
        _, totals = conversion_rate(
            db.session, date(2026, 5, 1), date(2026, 5, 31),
        )
        assert totals["total"] == 0
        assert totals["rate"]  == 0.0


# ── time_to_convert ──────────────────────────────────────


def test_time_to_convert_lists_paid_with_days():
    """Paid stores from the period each get a row with their
    `days` since signup."""
    from tests._app import app as flask_app, db
    from api.Modules.Superadmin.Services import time_to_convert
    with flask_app.app_context():
        db.session.query(Store).delete()
        db.session.commit()
        _add_store(db.session, slug="ttc-1", plan="basic",
                   created_at=datetime(2026, 5, 5))
        rows, totals = time_to_convert(
            db.session, date(2026, 5, 1), date(2026, 5, 31),
        )
        assert len(rows) == 1
        assert rows[0]["slug"] == "ttc-1"
        assert rows[0]["days"] >= 0
        assert totals["count"] == 1


def test_time_to_convert_excludes_trial_and_inactive():
    """Only basic/pro stores; trial / inactive don't count."""
    from tests._app import app as flask_app, db
    from api.Modules.Superadmin.Services import time_to_convert
    with flask_app.app_context():
        db.session.query(Store).delete()
        db.session.commit()
        _add_store(db.session, slug="ttc-trial", plan="trial",
                   created_at=datetime(2026, 5, 5))
        _add_store(db.session, slug="ttc-inact", plan="inactive",
                   created_at=datetime(2026, 5, 5))
        _add_store(db.session, slug="ttc-pro",   plan="pro",
                   created_at=datetime(2026, 5, 5))
        rows, totals = time_to_convert(
            db.session, date(2026, 5, 1), date(2026, 5, 31),
        )
        assert len(rows) == 1
        assert rows[0]["slug"] == "ttc-pro"
        assert totals["count"] == 1


def test_time_to_convert_avg_days_zero_when_empty():
    from tests._app import app as flask_app, db
    from api.Modules.Superadmin.Services import time_to_convert
    with flask_app.app_context():
        db.session.query(Store).delete()
        db.session.commit()
        _, totals = time_to_convert(
            db.session, date(2026, 5, 1), date(2026, 5, 31),
        )
        assert totals["count"]    == 0
        assert totals["avg_days"] == 0.0


# ── trial_expiry_timing ──────────────────────────────────


def test_trial_expiry_timing_buckets_by_age():
    """Trial stores bucketed by days since `created_at`."""
    from tests._app import app as flask_app, db
    from api.Modules.Superadmin.Services import trial_expiry_timing
    with flask_app.app_context():
        db.session.query(Store).delete()
        db.session.commit()
        today = datetime.utcnow()
        _add_store(db.session, slug="tet-3day", plan="trial",
                   created_at=today - timedelta(days=3))
        _add_store(db.session, slug="tet-10day", plan="trial",
                   created_at=today - timedelta(days=10))
        _add_store(db.session, slug="tet-25day", plan="trial",
                   created_at=today - timedelta(days=25))
        rows, totals = trial_expiry_timing(
            db.session, date(2026, 5, 1), date(2030, 12, 31),
        )
        by_bucket = {r["bucket"]: r["count"] for r in rows}
        assert by_bucket["≤ 7 days into trial"] == 1
        assert by_bucket["8–14 days"]           == 1
        assert by_bucket["22+ days"]            == 1
        assert totals["trials_total"] == 3


def test_trial_expiry_timing_expired_bucket():
    """Trial whose `trial_ends_at` is in the past lands in the
    expired bucket regardless of age."""
    from tests._app import app as flask_app, db
    from api.Modules.Superadmin.Services import trial_expiry_timing
    with flask_app.app_context():
        db.session.query(Store).delete()
        db.session.commit()
        today = datetime.utcnow()
        _add_store(db.session, slug="tet-expired", plan="trial",
                   created_at=today - timedelta(days=30),
                   trial_ends_at=today - timedelta(days=5))
        rows, _ = trial_expiry_timing(
            db.session, date(2026, 5, 1), date(2030, 12, 31),
        )
        assert rows[0]["bucket"] == "Trial expired (no upgrade)"


def test_trial_expiry_timing_skips_empty_buckets():
    """Buckets with 0 count are not emitted as rows."""
    from tests._app import app as flask_app, db
    from api.Modules.Superadmin.Services import trial_expiry_timing
    with flask_app.app_context():
        db.session.query(Store).delete()
        db.session.commit()
        _add_store(db.session, slug="tet-only-1", plan="trial",
                   created_at=datetime.utcnow() - timedelta(days=3))
        rows, _ = trial_expiry_timing(
            db.session, date(2026, 5, 1), date(2030, 12, 31),
        )
        # Only one bucket emitted ("≤ 7 days").
        assert len(rows) == 1


# ── legacy wrappers ──────────────────────────────────────






