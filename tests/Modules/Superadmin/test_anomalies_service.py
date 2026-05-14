"""Unit tests for Superadmin.Services.anomalies (PR 60).

Tests use the real ORM (transfers, daily reports, stores) to
exercise the GROUP BYs end-to-end. The Service builds an
impersonation URL via `flask.url_for` when called from a request
context — tests run inside `app_context()` (no request), so
`href` falls back to `""`. That fallback path is the CLI / test
behavior; the Flask route gets a real URL.
"""
from datetime import date, timedelta

from api.Modules.DailyBook.Models import DailyReport
from api.Modules.Tenancy.Models import Store
from api.Modules.Transfers.Models import Transfer


def _add_store(db, *, name="Test Co", slug=None,
               plan="basic", is_active=True):
    s = Store(
        name=name,
        slug=slug or name.lower().replace(" ", "-"),
        plan=plan,
        email=f"{slug or 'test'}@example.com",
        is_active=is_active,
    )
    db.add(s)
    db.flush()
    return s


def _add_transfer(db, store_id, *, send_date, send_amount=100.0,
                  status="completed"):
    """Create a minimal Transfer row. `total_collected` is a derived
    @property so we don't set it; nullable columns get defaults."""
    t = Transfer(
        store_id=store_id,
        send_date=send_date,
        company="Intermex",
        sender_name="Test Sender",
        send_amount=send_amount,
        fee=0.0,
        federal_tax=0.0,
        status=status,
    )
    db.add(t)
    db.flush()
    return t


def _add_report(db, store_id, *, report_date, over_short=0.0):
    r = DailyReport(
        store_id=store_id,
        report_date=report_date,
        over_short=over_short,
    )
    db.add(r)
    db.flush()
    return r


# ── compute_platform_anomalies ─────────────────────────────


def test_empty_db_returns_empty():
    """Fresh DB with no transfers / reports → empty list."""
    from tests._app import app as flask_app
    from tests._app import db
    from api.Modules.Superadmin.Services import compute_platform_anomalies
    with flask_app.app_context():
        # Wipe any seeded transfers/reports so this test is hermetic.
        Transfer.query.delete()
        DailyReport.query.delete()
        db.session.commit()
        assert compute_platform_anomalies(db.session) == []


# ── quiet-store rule ───────────────────────────────────────


def test_quiet_store_flagged_when_active_then_silent():
    """Store had ≥5 transfers in the last 30 days but none in the
    last 3 days → flagged 'quiet_store' / medium."""
    from tests._app import app as flask_app
    from tests._app import db
    from api.Modules.Superadmin.Services import quiet_store_anomalies
    with flask_app.app_context():
        Transfer.query.delete()
        db.session.commit()
        s = _add_store(db.session, slug="quiet-co")
        today = date.today()
        # 6 transfers, all > 3 days ago → still inside the 30-day
        # window but past the 3-day "recent" threshold.
        for i in range(6):
            _add_transfer(
                db.session, s.id,
                send_date=today - timedelta(days=10 + i),
            )
        db.session.commit()
        rows = quiet_store_anomalies(db.session, today)
        kinds = [r["kind"] for r in rows if r["store"].id == s.id]
        assert kinds == ["quiet_store"]
        match = next(r for r in rows if r["store"].id == s.id)
        assert match["severity"] == "medium"


def test_quiet_store_not_flagged_below_threshold():
    """Store with < 5 transfers in the last 30 days → not flagged
    (we don't yell about idle trials)."""
    from tests._app import app as flask_app
    from tests._app import db
    from api.Modules.Superadmin.Services import quiet_store_anomalies
    with flask_app.app_context():
        Transfer.query.delete()
        db.session.commit()
        s = _add_store(db.session, slug="tiny-co")
        today = date.today()
        # Only 4 transfers — below ANOMALY_QUIET_MIN_PRIOR_TRANSFERS.
        for i in range(4):
            _add_transfer(
                db.session, s.id,
                send_date=today - timedelta(days=10 + i),
            )
        db.session.commit()
        rows = quiet_store_anomalies(db.session, today)
        assert not any(r["store"].id == s.id for r in rows)


def test_quiet_store_not_flagged_when_recent_activity():
    """Recent transfer (within 3 days) → not flagged."""
    from tests._app import app as flask_app
    from tests._app import db
    from api.Modules.Superadmin.Services import quiet_store_anomalies
    with flask_app.app_context():
        Transfer.query.delete()
        db.session.commit()
        s = _add_store(db.session, slug="active-co")
        today = date.today()
        for i in range(6):
            _add_transfer(
                db.session, s.id,
                send_date=today - timedelta(days=i),  # includes today
            )
        db.session.commit()
        rows = quiet_store_anomalies(db.session, today)
        assert not any(r["store"].id == s.id for r in rows)


def test_quiet_store_skips_inactive_plan():
    """plan='inactive' (cancelled) → not flagged. Cancelled stores
    aren't anomalies."""
    from tests._app import app as flask_app
    from tests._app import db
    from api.Modules.Superadmin.Services import quiet_store_anomalies
    with flask_app.app_context():
        Transfer.query.delete()
        db.session.commit()
        s = _add_store(db.session, slug="cancelled-co", plan="inactive")
        today = date.today()
        for i in range(6):
            _add_transfer(
                db.session, s.id,
                send_date=today - timedelta(days=10 + i),
            )
        db.session.commit()
        rows = quiet_store_anomalies(db.session, today)
        assert not any(r["store"].id == s.id for r in rows)


def test_quiet_store_skips_inactive_store_flag():
    """is_active=False → not flagged."""
    from tests._app import app as flask_app
    from tests._app import db
    from api.Modules.Superadmin.Services import quiet_store_anomalies
    with flask_app.app_context():
        Transfer.query.delete()
        db.session.commit()
        s = _add_store(db.session, slug="disabled-co", is_active=False)
        today = date.today()
        for i in range(6):
            _add_transfer(
                db.session, s.id,
                send_date=today - timedelta(days=10 + i),
            )
        db.session.commit()
        rows = quiet_store_anomalies(db.session, today)
        assert not any(r["store"].id == s.id for r in rows)


# ── over/short rule ────────────────────────────────────────


def test_big_over_short_high_severity_at_or_above_high_threshold():
    """|over_short| ≥ $200 → severity 'high'."""
    from tests._app import app as flask_app
    from tests._app import db
    from api.Modules.Superadmin.Services import big_over_short_anomalies
    with flask_app.app_context():
        DailyReport.query.delete()
        db.session.commit()
        s = _add_store(db.session, slug="varianty-co")
        today = date.today()
        _add_report(
            db.session, s.id,
            report_date=today - timedelta(days=2),
            over_short=-225.0,  # short by $225
        )
        db.session.commit()
        rows = big_over_short_anomalies(db.session, today)
        match = next(r for r in rows if r["store"].id == s.id)
        assert match["severity"] == "high"
        assert "short" in match["description"]


def test_big_over_short_medium_severity_in_band():
    """$100 ≤ |over_short| < $200 → severity 'medium'."""
    from tests._app import app as flask_app
    from tests._app import db
    from api.Modules.Superadmin.Services import big_over_short_anomalies
    with flask_app.app_context():
        DailyReport.query.delete()
        db.session.commit()
        s = _add_store(db.session, slug="medium-co")
        today = date.today()
        _add_report(
            db.session, s.id,
            report_date=today - timedelta(days=1),
            over_short=125.0,  # over by $125
        )
        db.session.commit()
        rows = big_over_short_anomalies(db.session, today)
        match = next(r for r in rows if r["store"].id == s.id)
        assert match["severity"] == "medium"
        assert "over" in match["description"]


def test_big_over_short_below_threshold_excluded():
    """|over_short| < $100 → not flagged."""
    from tests._app import app as flask_app
    from tests._app import db
    from api.Modules.Superadmin.Services import big_over_short_anomalies
    with flask_app.app_context():
        DailyReport.query.delete()
        db.session.commit()
        s = _add_store(db.session, slug="small-variance-co")
        today = date.today()
        _add_report(
            db.session, s.id,
            report_date=today - timedelta(days=1),
            over_short=50.0,
        )
        db.session.commit()
        rows = big_over_short_anomalies(db.session, today)
        assert not any(r["store"].id == s.id for r in rows)


def test_big_over_short_outside_lookback_window_excluded():
    """Reports older than 7 days are excluded."""
    from tests._app import app as flask_app
    from tests._app import db
    from api.Modules.Superadmin.Services import big_over_short_anomalies
    with flask_app.app_context():
        DailyReport.query.delete()
        db.session.commit()
        s = _add_store(db.session, slug="ancient-co")
        today = date.today()
        _add_report(
            db.session, s.id,
            report_date=today - timedelta(days=14),  # 2 weeks ago
            over_short=-400.0,
        )
        db.session.commit()
        rows = big_over_short_anomalies(db.session, today)
        assert not any(r["store"].id == s.id for r in rows)


# ── ranking + cap ──────────────────────────────────────────


def test_compute_ranks_high_before_medium():
    """High-severity items float to the top of the merged list."""
    from tests._app import app as flask_app
    from tests._app import db
    from api.Modules.Superadmin.Services import compute_platform_anomalies
    with flask_app.app_context():
        Transfer.query.delete()
        DailyReport.query.delete()
        db.session.commit()
        # One quiet-store (medium), one big-over-short high.
        sq = _add_store(db.session, slug="qq")
        sb = _add_store(db.session, slug="bb")
        today = date.today()
        for i in range(6):
            _add_transfer(
                db.session, sq.id,
                send_date=today - timedelta(days=10 + i),
            )
        _add_report(
            db.session, sb.id,
            report_date=today - timedelta(days=1),
            over_short=-300.0,  # high
        )
        db.session.commit()
        rows = compute_platform_anomalies(db.session)
        # High comes first.
        severities = [r["severity"] for r in rows]
        assert severities.index("high") < severities.index("medium")


# ── legacy Flask wrapper ───────────────────────────────────




