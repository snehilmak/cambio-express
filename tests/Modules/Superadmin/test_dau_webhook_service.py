"""Unit tests for SA dau_mau + webhook_health services (PR 103)."""
from datetime import date, datetime, timedelta

from api.Modules.Auth.Models import LoginEvent
from api.Modules.Tenancy.Models import User
from api.Modules.Webhooks.Models import WebhookEvent


def _add_user(db, *, role="admin", username):
    u = User(
        username=username,
        full_name="X",
        password_hash="hash",
        role=role,
    )
    db.add(u); db.flush()
    return u


def _add_login(db, user_id, *, at, role="admin"):
    e = LoginEvent(user_id=user_id, role=role, at=at)
    db.add(e); db.flush()
    return e


def _add_webhook(db, *, status="ok",
                 received_at=None, event_type="charge.succeeded"):
    w = WebhookEvent(
        received_at=received_at or datetime.utcnow(),
        source="stripe",
        event_type=event_type,
        status=status,
    )
    db.add(w); db.flush()
    return w


# ── dau_mau ─────────────────────────────────────────────


def test_dau_mau_distinct_users_per_day():
    """Same user logging twice in a day still counts as 1 in
    that day's bucket."""
    from app import app as flask_app, db
    from api.Modules.Superadmin.Services import dau_mau
    with flask_app.app_context():
        LoginEvent.query.delete()
        db.session.commit()
        u1 = _add_user(db.session, username="dm-u1")
        u2 = _add_user(db.session, username="dm-u2")
        _add_login(db.session, u1.id, at=datetime(2026, 5, 5, 9))
        _add_login(db.session, u1.id, at=datetime(2026, 5, 5, 14))
        _add_login(db.session, u2.id, at=datetime(2026, 5, 5, 10))
        _add_login(db.session, u1.id, at=datetime(2026, 5, 6, 9))
        rows, totals = dau_mau(
            db.session, date(2026, 5, 1), date(2026, 5, 31),
        )
        # 2 distinct days with logins.
        assert totals["active_days"] == 2
        # Day 5 had 2 distinct users (u1, u2). Day 6 had 1 (u1).
        by_day = {r["day"]: r["users"] for r in rows}
        five = next(d for d in by_day if str(d).endswith("05"))
        six  = next(d for d in by_day if str(d).endswith("06"))
        assert by_day[five] == 2
        assert by_day[six]  == 1
        # MAU = 2 distinct users in window.
        assert totals["mau"] == 2


def test_dau_mau_handles_zero_activity():
    """Empty window → zero rows, zero MAU/DAU, no divide-by-zero
    on stickiness."""
    from app import app as flask_app, db
    from api.Modules.Superadmin.Services import dau_mau
    with flask_app.app_context():
        LoginEvent.query.delete()
        db.session.commit()
        rows, totals = dau_mau(
            db.session, date(2020, 1, 1), date(2020, 1, 31),
        )
        assert rows == []
        assert totals["dau"]         == 0
        assert totals["mau"]         == 0
        assert totals["stickiness"]  == 0.0
        assert totals["avg_per_day"] == 0.0


def test_dau_mau_avg_per_day_uses_active_day_count():
    """avg_per_day = total user-day count / number of active days,
    not / number of calendar days in the window."""
    from app import app as flask_app, db
    from api.Modules.Superadmin.Services import dau_mau
    with flask_app.app_context():
        LoginEvent.query.delete()
        db.session.commit()
        u1 = _add_user(db.session, username="dm-avg-1")
        u2 = _add_user(db.session, username="dm-avg-2")
        # 2 days × 2 users = 4 user-day events.
        _add_login(db.session, u1.id, at=datetime(2026, 5, 5))
        _add_login(db.session, u2.id, at=datetime(2026, 5, 5))
        _add_login(db.session, u1.id, at=datetime(2026, 5, 10))
        _add_login(db.session, u2.id, at=datetime(2026, 5, 10))
        _, totals = dau_mau(
            db.session, date(2026, 5, 1), date(2026, 5, 31),
        )
        # 2 active days × 2 users-per-day = 4 user-days; avg = 2.
        assert totals["active_days"] == 2
        assert totals["avg_per_day"] == 2.0


# ── webhook_health ──────────────────────────────────────


def test_webhook_health_groups_by_status_with_failure_pct():
    """ok counts toward `ok`; everything else (signature_err,
    processing_err, etc.) counts toward `errors`. failure_pct
    = errors / count * 100."""
    from app import app as flask_app, db
    from api.Modules.Superadmin.Services import webhook_health
    with flask_app.app_context():
        WebhookEvent.query.delete()
        db.session.commit()
        for _ in range(8):
            _add_webhook(
                db.session, status="ok",
                received_at=datetime(2026, 5, 5),
            )
        for _ in range(2):
            _add_webhook(
                db.session, status="signature_err",
                received_at=datetime(2026, 5, 5),
            )
        rows, totals = webhook_health(
            db.session, date(2026, 5, 1), date(2026, 5, 31),
        )
        by_status = {r["status_key"]: r for r in rows}
        assert by_status["ok"]["count"]            == 8
        assert by_status["signature_err"]["count"] == 2
        # Display label: underscores replaced + title-case.
        assert by_status["signature_err"]["status"] == "Signature Err"
        assert totals["count"]       == 10
        assert totals["ok"]          == 8
        assert totals["errors"]      == 2
        assert totals["failure_pct"] == 20.0


def test_webhook_health_zero_count_no_div_by_zero():
    from app import app as flask_app, db
    from api.Modules.Superadmin.Services import webhook_health
    with flask_app.app_context():
        WebhookEvent.query.delete()
        db.session.commit()
        rows, totals = webhook_health(
            db.session, date(2026, 5, 1), date(2026, 5, 31),
        )
        assert rows == []
        assert totals["count"]       == 0
        assert totals["failure_pct"] == 0.0


def test_webhook_health_filters_by_received_at_window():
    from app import app as flask_app, db
    from api.Modules.Superadmin.Services import webhook_health
    with flask_app.app_context():
        WebhookEvent.query.delete()
        db.session.commit()
        _add_webhook(
            db.session, status="ok",
            received_at=datetime(2026, 4, 30),
        )
        _add_webhook(
            db.session, status="ok",
            received_at=datetime(2026, 5, 15),
        )
        _, totals = webhook_health(
            db.session, date(2026, 5, 1), date(2026, 5, 31),
        )
        assert totals["count"] == 1


# ── legacy wrappers ──────────────────────────────────────


def test_legacy_dau_mau_wrapper_delegates():
    from app import app as flask_app, db
    from app import _sa_dau_mau_data
    from api.Modules.Superadmin.Services import dau_mau
    with flask_app.app_context():
        LoginEvent.query.delete()
        db.session.commit()
        u = _add_user(db.session, username="dm-leg")
        _add_login(db.session, u.id, at=datetime(2026, 5, 5))
        legacy = _sa_dau_mau_data(date(2026, 5, 1), date(2026, 5, 31))
        svc = dau_mau(
            db.session, date(2026, 5, 1), date(2026, 5, 31),
        )
        assert legacy == svc


def test_legacy_webhook_health_wrapper_delegates():
    from app import app as flask_app, db
    from app import _sa_webhook_health_data
    from api.Modules.Superadmin.Services import webhook_health
    with flask_app.app_context():
        WebhookEvent.query.delete()
        db.session.commit()
        _add_webhook(db.session, status="ok",
                     received_at=datetime(2026, 5, 5))
        legacy = _sa_webhook_health_data(
            date(2026, 5, 1), date(2026, 5, 31),
        )
        svc = webhook_health(
            db.session, date(2026, 5, 1), date(2026, 5, 31),
        )
        assert legacy == svc
