"""Unit tests for SA password_resets / suspended_stores /
retention_queue services (PR 101).
"""
from datetime import date, datetime, timedelta

from api.Modules.Auth.Models import PasswordResetToken
from api.Modules.Tenancy.Models import Store, User
from tests._app import db


_USER_COUNTER = 0
_TOKEN_COUNTER = 0


def _add_user(db, *, role="admin", username=None, full_name="X"):
    global _USER_COUNTER
    _USER_COUNTER += 1
    u = User(
        username=username or f"sa-pw-{_USER_COUNTER}",
        full_name=full_name,
        password_hash="hash",
        role=role,
    )
    db.add(u); db.flush()
    return u


def _add_token(db, user_id, *, created_at, expires_at,
               used_at=None):
    global _TOKEN_COUNTER
    _TOKEN_COUNTER += 1
    t = PasswordResetToken(
        user_id=user_id,
        token_hash=f"hash-{_TOKEN_COUNTER}",
        created_at=created_at,
        expires_at=expires_at,
        used_at=used_at,
    )
    db.add(t); db.flush()
    return t


def _add_store(db, *, slug, plan="basic", is_active=True,
               canceled_at=None, data_retention_until=None,
               created_at=None):
    s = Store(name=slug, slug=slug, plan=plan,
              is_active=is_active,
              canceled_at=canceled_at,
              data_retention_until=data_retention_until,
              email=f"{slug}@example.com",
              created_at=created_at or datetime.utcnow())
    db.add(s); db.flush()
    return s


# ── password_resets ─────────────────────────────────────


def test_password_resets_classifies_used_expired_open():
    """Each token classified as Used / Expired / Open."""
    from tests._app import app as flask_app, db
    from api.Modules.Superadmin.Services import password_resets
    with flask_app.app_context():
        db.session.query(PasswordResetToken).delete()
        db.session.commit()
        u = _add_user(db.session, role="admin")
        now = datetime.utcnow()
        # Used.
        _add_token(db.session, u.id,
                   created_at=datetime(2026, 5, 5),
                   expires_at=now + timedelta(hours=1),
                   used_at=datetime(2026, 5, 5, 1, 0))
        # Expired (no used_at, expires_at in past).
        _add_token(db.session, u.id,
                   created_at=datetime(2026, 5, 6),
                   expires_at=now - timedelta(hours=1))
        # Open (not used, expires later).
        _add_token(db.session, u.id,
                   created_at=datetime(2026, 5, 7),
                   expires_at=now + timedelta(hours=5))
        rows, totals = password_resets(
            db.session, date(2026, 5, 1), date(2026, 5, 31),
        )
        statuses = sorted(r["status"] for r in rows)
        assert statuses == ["Expired", "Open", "Used"]
        assert totals["used"]    == 1
        assert totals["expired"] == 1
        assert totals["open"]    == 1
        assert totals["count"]   == 3


def test_password_resets_handles_deleted_user():
    """Token whose user was deleted shows '(deleted)' username."""
    from tests._app import app as flask_app, db
    from api.Modules.Superadmin.Services import password_resets
    with flask_app.app_context():
        db.session.query(PasswordResetToken).delete()
        db.session.commit()
        # Insert a token referencing a user_id that doesn't exist.
        t = PasswordResetToken(
            user_id=99999,
            token_hash="orphan-hash",
            created_at=datetime(2026, 5, 5),
            expires_at=datetime.utcnow() + timedelta(hours=1),
        )
        db.session.add(t)
        db.session.commit()
        rows, _ = password_resets(
            db.session, date(2026, 5, 1), date(2026, 5, 31),
        )
        assert rows[0]["username"] == "(deleted)"


def test_password_resets_window_filter():
    from tests._app import app as flask_app, db
    from api.Modules.Superadmin.Services import password_resets
    with flask_app.app_context():
        db.session.query(PasswordResetToken).delete()
        db.session.commit()
        u = _add_user(db.session, role="admin")
        now = datetime.utcnow() + timedelta(hours=1)
        _add_token(db.session, u.id,
                   created_at=datetime(2026, 4, 30),
                   expires_at=now)
        _add_token(db.session, u.id,
                   created_at=datetime(2026, 5, 15),
                   expires_at=now)
        _, totals = password_resets(
            db.session, date(2026, 5, 1), date(2026, 5, 31),
        )
        assert totals["count"] == 1


# ── suspended_stores ────────────────────────────────────


def test_suspended_stores_includes_inactive_flag():
    from tests._app import app as flask_app, db
    from api.Modules.Superadmin.Services import suspended_stores
    with flask_app.app_context():
        db.session.query(Store).delete()
        db.session.commit()
        _add_store(db.session, slug="ss-active", plan="basic",
                   is_active=True)
        _add_store(db.session, slug="ss-suspended", plan="basic",
                   is_active=False)
        _add_store(db.session, slug="ss-inactive-plan",
                   plan="inactive",
                   is_active=True)
        rows, totals = suspended_stores(
            db.session, date(2026, 5, 1), date(2026, 5, 31),
        )
        slugs = {r["slug"] for r in rows}
        assert slugs == {"ss-suspended", "ss-inactive-plan"}
        assert totals["count"] == 2


def test_suspended_stores_reason_combines_flags():
    """A store with BOTH is_active=False AND plan=inactive should
    have both reasons in the row."""
    from tests._app import app as flask_app, db
    from api.Modules.Superadmin.Services import suspended_stores
    with flask_app.app_context():
        db.session.query(Store).delete()
        db.session.commit()
        _add_store(db.session, slug="ss-both",
                   plan="inactive",
                   is_active=False)
        rows, _ = suspended_stores(
            db.session, date(2026, 5, 1), date(2026, 5, 31),
        )
        assert "suspended" in rows[0]["reason"]
        assert "plan inactive" in rows[0]["reason"]


# ── retention_queue ─────────────────────────────────────


def test_retention_queue_only_includes_stores_with_until_set():
    from tests._app import app as flask_app, db
    from api.Modules.Superadmin.Services import retention_queue
    with flask_app.app_context():
        db.session.query(Store).delete()
        db.session.commit()
        _add_store(db.session, slug="rq-no-until", plan="basic",
                   data_retention_until=None)
        _add_store(db.session, slug="rq-pending", plan="inactive",
                   data_retention_until=datetime.utcnow()
                       + timedelta(days=30))
        rows, _ = retention_queue(
            db.session, date(2026, 5, 1), date(2026, 5, 31),
        )
        assert len(rows) == 1
        assert rows[0]["slug"] == "rq-pending"
        assert rows[0]["days_left"] >= 0


def test_retention_queue_ready_to_purge_when_days_negative():
    """When `until` is in the past, `ready_to_purge` is True."""
    from tests._app import app as flask_app, db
    from api.Modules.Superadmin.Services import retention_queue
    with flask_app.app_context():
        db.session.query(Store).delete()
        db.session.commit()
        _add_store(db.session, slug="rq-ready", plan="inactive",
                   data_retention_until=datetime.utcnow()
                       - timedelta(days=5))
        rows, totals = retention_queue(
            db.session, date(2026, 5, 1), date(2026, 5, 31),
        )
        assert rows[0]["ready_to_purge"] is True
        assert totals["ready_to_purge"] == 1


# ── legacy wrappers ──────────────────────────────────────






