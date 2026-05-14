"""Unit tests for Announcements.Services.visibility (PR 55)."""
from datetime import datetime, timedelta


def _add_announcement(db_session, **kwargs):
    """Build + add an Announcement row using the legacy ORM."""
    from api.Modules.Announcements.Models import Announcement
    a = Announcement(
        message=kwargs.pop("message", "hello"),
        level=kwargs.pop("level", "info"),
        is_active=kwargs.pop("is_active", True),
        starts_at=kwargs.pop("starts_at", None),
        expires_at=kwargs.pop("expires_at", None),
    )
    db_session.add(a)
    db_session.flush()
    return a


# ── visibility filter ──────────────────────────────────────


def test_returns_active_with_no_window():
    """Active row with no starts_at/expires_at is always visible."""
    from tests._app import app as flask_app, db
    from api.Modules.Announcements.Services import active_announcements
    with flask_app.app_context():
        a = _add_announcement(db.session, message="always-on")
        rows = active_announcements(db.session)
        assert a in rows


def test_filters_inactive_rows():
    """is_active=False is hidden even when in window."""
    from tests._app import app as flask_app, db
    from api.Modules.Announcements.Services import active_announcements
    with flask_app.app_context():
        a = _add_announcement(
            db.session, message="hidden", is_active=False,
        )
        rows = active_announcements(db.session)
        assert a not in rows


def test_filters_future_starts_at():
    """starts_at in the future → hidden."""
    from tests._app import app as flask_app, db
    from api.Modules.Announcements.Services import active_announcements
    with flask_app.app_context():
        future = datetime.utcnow() + timedelta(days=1)
        a = _add_announcement(
            db.session, message="not yet", starts_at=future,
        )
        assert a not in active_announcements(db.session)


def test_includes_past_starts_at():
    """starts_at already past → visible."""
    from tests._app import app as flask_app, db
    from api.Modules.Announcements.Services import active_announcements
    with flask_app.app_context():
        past = datetime.utcnow() - timedelta(hours=1)
        a = _add_announcement(
            db.session, message="started", starts_at=past,
        )
        assert a in active_announcements(db.session)


def test_filters_expired_rows():
    """expires_at in the past → hidden."""
    from tests._app import app as flask_app, db
    from api.Modules.Announcements.Services import active_announcements
    with flask_app.app_context():
        past = datetime.utcnow() - timedelta(hours=1)
        a = _add_announcement(
            db.session, message="expired", expires_at=past,
        )
        assert a not in active_announcements(db.session)


def test_includes_future_expires_at():
    """expires_at still in the future → visible."""
    from tests._app import app as flask_app, db
    from api.Modules.Announcements.Services import active_announcements
    with flask_app.app_context():
        future = datetime.utcnow() + timedelta(days=1)
        a = _add_announcement(
            db.session, message="not yet expired", expires_at=future,
        )
        assert a in active_announcements(db.session)


def test_includes_full_window_open():
    """Both starts_at past + expires_at future + active → visible."""
    from tests._app import app as flask_app, db
    from api.Modules.Announcements.Services import active_announcements
    with flask_app.app_context():
        a = _add_announcement(
            db.session,
            message="in window",
            starts_at=datetime.utcnow() - timedelta(hours=1),
            expires_at=datetime.utcnow() + timedelta(hours=1),
        )
        assert a in active_announcements(db.session)


def test_orders_newest_first():
    """Most recent created_at lands at the top of the banner stack."""
    from tests._app import app as flask_app, db
    from api.Modules.Announcements.Services import active_announcements
    with flask_app.app_context():
        # Emulate ordering by inserting two rows; created_at defaults
        # to utcnow() which is monotonically increasing within the
        # test (microsecond resolution is enough).
        a1 = _add_announcement(db.session, message="first")
        a2 = _add_announcement(db.session, message="second")
        rows = active_announcements(db.session)
        # a2 was inserted later → comes first.
        idx1 = rows.index(a1)
        idx2 = rows.index(a2)
        assert idx2 < idx1


# ── legacy Flask wrapper ───────────────────────────────────


