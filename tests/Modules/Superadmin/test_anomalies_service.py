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
from tests._app import db, db_session


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
    from tests._app import db
    from api.Modules.Superadmin.Services import compute_platform_anomalies
    with db_session():
        # Wipe any seeded transfers/reports so this test is hermetic.
        db.session.query(Transfer).delete()
        db.session.query(DailyReport).delete()
        db.session.commit()
        assert compute_platform_anomalies(db.session) == []


# ── quiet-store rule ───────────────────────────────────────


def test_quiet_store_flagged_when_active_then_silent():
    """Store had ≥5 transfers in the last 30 days but none in the
    last 3 days → flagged 'quiet_store' / medium."""
    from tests._app import db
    from api.Modules.Superadmin.Services import quiet_store_anomalies
    with db_session():
        db.session.query(Transfer).delete()
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
    from tests._app import db
    from api.Modules.Superadmin.Services import quiet_store_anomalies
    with db_session():
        db.session.query(Transfer).delete()
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
    from tests._app import db
    from api.Modules.Superadmin.Services import quiet_store_anomalies
    with db_session():
        db.session.query(Transfer).delete()
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
    from tests._app import db
    from api.Modules.Superadmin.Services import quiet_store_anomalies
    with db_session():
        db.session.query(Transfer).delete()
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
    from tests._app import db
    from api.Modules.Superadmin.Services import quiet_store_anomalies
    with db_session():
        db.session.query(Transfer).delete()
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
    from tests._app import db
    from api.Modules.Superadmin.Services import big_over_short_anomalies
    with db_session():
        db.session.query(DailyReport).delete()
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
    from tests._app import db
    from api.Modules.Superadmin.Services import big_over_short_anomalies
    with db_session():
        db.session.query(DailyReport).delete()
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
    from tests._app import db
    from api.Modules.Superadmin.Services import big_over_short_anomalies
    with db_session():
        db.session.query(DailyReport).delete()
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
    from tests._app import db
    from api.Modules.Superadmin.Services import big_over_short_anomalies
    with db_session():
        db.session.query(DailyReport).delete()
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
    from tests._app import db
    from api.Modules.Superadmin.Services import compute_platform_anomalies
    with db_session():
        db.session.query(Transfer).delete()
        db.session.query(DailyReport).delete()
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


# ── cancellation-spike rule ────────────────────────────────


def _set_canceled(store, when):
    """Stamp a cancellation timestamp on `store`. Mirrors what
    the Stripe webhook handler does, but skips the audit + plan
    flip so tests stay tight on the anomaly rule."""
    store.canceled_at = when


def test_cancellation_spike_silent_below_threshold():
    """One or two cancellations in 24h is normal noise — the rule
    must stay silent below ANOMALY_CANCELLATION_SPIKE_THRESHOLD."""
    from datetime import datetime
    from tests._app import db
    from api.Modules.Superadmin.Services import (
        ANOMALY_CANCELLATION_SPIKE_THRESHOLD,
        cancellation_spike_anomalies,
    )
    with db_session():
        # Wipe any prior cancels so the test is hermetic.
        db.session.query(Store).filter(
            Store.canceled_at.isnot(None),
        ).update({"canceled_at": None}, synchronize_session=False)
        db.session.commit()
        now = datetime.utcnow()
        # ONE less than the threshold.
        for i in range(ANOMALY_CANCELLATION_SPIKE_THRESHOLD - 1):
            s = _add_store(db.session, slug=f"sub-{i}")
            _set_canceled(s, now - timedelta(hours=2))
        db.session.commit()
        assert cancellation_spike_anomalies(db.session, now) == []


def test_cancellation_spike_returns_row_per_store_at_threshold():
    """At-or-above threshold → one anomaly row per cancelled
    store, all marked high severity."""
    from datetime import datetime
    from tests._app import db
    from api.Modules.Superadmin.Services import (
        ANOMALY_CANCELLATION_SPIKE_THRESHOLD,
        cancellation_spike_anomalies,
    )
    with db_session():
        db.session.query(Store).filter(
            Store.canceled_at.isnot(None),
        ).update({"canceled_at": None}, synchronize_session=False)
        db.session.commit()
        now = datetime.utcnow()
        slugs = [
            f"burst-{i}"
            for i in range(ANOMALY_CANCELLATION_SPIKE_THRESHOLD)
        ]
        for slug in slugs:
            s = _add_store(db.session, slug=slug)
            _set_canceled(s, now - timedelta(hours=3))
        db.session.commit()
        rows = cancellation_spike_anomalies(db.session, now)
        assert len(rows) == ANOMALY_CANCELLATION_SPIKE_THRESHOLD
        assert all(r["kind"] == "cancellation_spike" for r in rows)
        assert all(r["severity"] == "high" for r in rows)
        result_slugs = {r["store"].slug for r in rows}
        assert result_slugs == set(slugs)


def test_cancellation_spike_ignores_old_cancels():
    """A cancellation from 48h ago is outside the 24h window —
    must NOT count toward the spike threshold."""
    from datetime import datetime
    from tests._app import db
    from api.Modules.Superadmin.Services import (
        ANOMALY_CANCELLATION_LOOKBACK_HOURS,
        ANOMALY_CANCELLATION_SPIKE_THRESHOLD,
        cancellation_spike_anomalies,
    )
    with db_session():
        db.session.query(Store).filter(
            Store.canceled_at.isnot(None),
        ).update({"canceled_at": None}, synchronize_session=False)
        db.session.commit()
        now = datetime.utcnow()
        # Stale cancels — beyond the lookback window.
        for i in range(ANOMALY_CANCELLATION_SPIKE_THRESHOLD + 2):
            s = _add_store(db.session, slug=f"old-{i}")
            _set_canceled(
                s,
                now - timedelta(
                    hours=ANOMALY_CANCELLATION_LOOKBACK_HOURS + 2,
                ),
            )
        db.session.commit()
        assert cancellation_spike_anomalies(db.session, now) == []


# ── password-reset-spike rule ──────────────────────────────


def _make_user_with_resets(db, *, store_id, username, count, since):
    """Create a User + N PasswordResetToken rows stamped `since`."""
    from api.Modules.Auth.Models import PasswordResetToken
    from api.Modules.Tenancy.Models import User
    u = User(
        username=username, password_hash="x", role="admin",
        full_name="x", email=username, store_id=store_id,
    )
    db.add(u)
    db.flush()
    for i in range(count):
        db.add(PasswordResetToken(
            user_id=u.id,
            token_hash=f"hash-{username}-{i}",
            expires_at=since + timedelta(hours=1),
            created_at=since,
        ))
    return u


def test_password_reset_spike_silent_below_threshold():
    """Less than the per-user threshold → silent."""
    from datetime import datetime
    from tests._app import db
    from api.Modules.Auth.Models import PasswordResetToken
    from api.Modules.Superadmin.Services import (
        ANOMALY_PASSWORD_RESET_PER_USER_THRESHOLD,
        password_reset_spike_anomalies,
    )
    with db_session():
        db.session.query(PasswordResetToken).delete()
        db.session.commit()
        s = _add_store(db.session, slug="prs-low")
        now = datetime.utcnow()
        _make_user_with_resets(
            db.session, store_id=s.id, username="quiet@test.com",
            count=ANOMALY_PASSWORD_RESET_PER_USER_THRESHOLD - 1,
            since=now - timedelta(hours=1),
        )
        db.session.commit()
        assert password_reset_spike_anomalies(db.session, now) == []


def test_password_reset_spike_returns_row_per_burst_user():
    """At-or-above threshold for a user → one medium-severity
    anomaly row attached to that user's store."""
    from datetime import datetime
    from tests._app import db
    from api.Modules.Auth.Models import PasswordResetToken
    from api.Modules.Superadmin.Services import (
        ANOMALY_PASSWORD_RESET_PER_USER_THRESHOLD,
        password_reset_spike_anomalies,
    )
    with db_session():
        db.session.query(PasswordResetToken).delete()
        db.session.commit()
        s = _add_store(db.session, slug="prs-burst")
        now = datetime.utcnow()
        target = _make_user_with_resets(
            db.session, store_id=s.id, username="suspect@test.com",
            count=ANOMALY_PASSWORD_RESET_PER_USER_THRESHOLD,
            since=now - timedelta(hours=1),
        )
        # An unrelated user well under threshold — must not
        # produce a row.
        _make_user_with_resets(
            db.session, store_id=s.id, username="normal@test.com",
            count=1, since=now - timedelta(hours=1),
        )
        db.session.commit()
        rows = password_reset_spike_anomalies(db.session, now)
        assert len(rows) == 1
        row = rows[0]
        assert row["kind"] == "password_reset_spike"
        assert row["severity"] == "medium"
        assert row["store"].id == s.id
        assert "suspect@test.com" in row["description"]
        # The under-threshold user's email is NOT in any row.
        assert all("normal@test.com" not in r["description"] for r in rows)
        # Sanity: the burst user is the target we made.
        assert target.id is not None


def test_password_reset_spike_ignores_old_tokens():
    """Tokens stamped > lookback window ago don't count, even if
    the user has many of them."""
    from datetime import datetime
    from tests._app import db
    from api.Modules.Auth.Models import PasswordResetToken
    from api.Modules.Superadmin.Services import (
        ANOMALY_PASSWORD_RESET_LOOKBACK_HOURS,
        ANOMALY_PASSWORD_RESET_PER_USER_THRESHOLD,
        password_reset_spike_anomalies,
    )
    with db_session():
        db.session.query(PasswordResetToken).delete()
        db.session.commit()
        s = _add_store(db.session, slug="prs-stale")
        now = datetime.utcnow()
        _make_user_with_resets(
            db.session, store_id=s.id, username="stale@test.com",
            count=ANOMALY_PASSWORD_RESET_PER_USER_THRESHOLD + 5,
            since=now - timedelta(
                hours=ANOMALY_PASSWORD_RESET_LOOKBACK_HOURS + 2,
            ),
        )
        db.session.commit()
        assert password_reset_spike_anomalies(db.session, now) == []
