"""HTTP integration tests for the Announcements Controllers.

Mounts at /api/v2/announcements/*. Superadmin-scoped CRUD over the
global banner the legacy /superadmin/controls page already manages.
"""
from datetime import datetime, timedelta


def _login_admin(client, store_id):
    resp = client.post(
        "/api/v2/auth/login",
        json={
            "username": "admin@test.com",
            "password": "testpass123!",
            "store_id": store_id,
        },
    )
    return resp.get_json()["access_token"]


def _login_superadmin(client):
    """Wraps the SPA two-step login (password → TOTP exchange)
    using the seeded superadmin's pre-enrolled TOTP secret. See
    tests/conftest.py for the secret + helper definition."""
    from tests.conftest import login_superadmin
    return login_superadmin(client)


def _seed(message="Heads up", level="info", is_active=True,
          starts_at=None, expires_at=None):
    from api.Modules.Announcements.Models import Announcement
    from tests._app import db
    a = Announcement(
        message=message, level=level, is_active=is_active,
        starts_at=starts_at, expires_at=expires_at,
    )
    db.session.add(a); db.session.commit()
    return a.id


# ── Auth gating ─────────────────────────────────────────────


def test_list_requires_jwt(client):
    resp = client.get("/api/v2/announcements")
    assert resp.status_code == 401


def test_list_rejects_admin_role(client, test_store_id):
    token = _login_admin(client, test_store_id)
    resp = client.get(
        "/api/v2/announcements",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403


def test_create_rejects_admin_role(client, test_store_id):
    token = _login_admin(client, test_store_id)
    resp = client.post(
        "/api/v2/announcements",
        json={"message": "x"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403


# ── Schema validation ───────────────────────────────────────


def test_create_rejects_empty_message(client):
    token = _login_superadmin(client)
    resp = client.post(
        "/api/v2/announcements",
        json={"message": ""},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422


def test_create_rejects_invalid_level(client):
    token = _login_superadmin(client)
    resp = client.post(
        "/api/v2/announcements",
        json={"message": "x", "level": "neon-pink"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422


def test_create_rejects_extra_fields(client):
    """Pydantic schema is extra="forbid" — typos must 422."""
    token = _login_superadmin(client)
    resp = client.post(
        "/api/v2/announcements",
        json={"message": "x", "color": "red"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422


# ── Happy paths ─────────────────────────────────────────────


def test_create_returns_row_and_persists(client):
    token = _login_superadmin(client)
    resp = client.post(
        "/api/v2/announcements",
        json={"message": "Maintenance window Friday", "level": "warning",
              "expires_days": 3},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201
    body = resp.get_json()
    a = body["announcement"]
    assert a["message"] == "Maintenance window Friday"
    assert a["level"] == "warning"
    assert a["is_active"] is True
    assert a["is_visible"] is True
    assert a["expires_at"]


def test_list_returns_newest_first(client):
    from tests._app import app as flask_app
    with flask_app.app_context():
        old_id = _seed(message="oldest")
        new_id = _seed(message="newest")
    token = _login_superadmin(client)
    body = client.get(
        "/api/v2/announcements",
        headers={"Authorization": f"Bearer {token}"},
    ).get_json()
    ids = [a["id"] for a in body["rows"]]
    assert ids[0] == new_id
    assert ids[-1] == old_id


def test_list_marks_expired_as_not_visible(client):
    from tests._app import app as flask_app
    with flask_app.app_context():
        past = datetime.utcnow() - timedelta(days=1)
        _seed(message="dead", expires_at=past)
    token = _login_superadmin(client)
    body = client.get(
        "/api/v2/announcements",
        headers={"Authorization": f"Bearer {token}"},
    ).get_json()
    row = next(a for a in body["rows"] if a["message"] == "dead")
    assert row["is_visible"] is False


def test_toggle_flips_is_active(client):
    from tests._app import app as flask_app
    with flask_app.app_context():
        ann_id = _seed(message="x", is_active=True)
    token = _login_superadmin(client)
    resp = client.post(
        f"/api/v2/announcements/{ann_id}/toggle",
        json={"is_active": False},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.get_json()["announcement"]["is_active"] is False


def test_toggle_404_when_missing(client):
    token = _login_superadmin(client)
    resp = client.post(
        "/api/v2/announcements/9999999/toggle",
        json={"is_active": False},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404


def test_delete_removes_row(client):
    from api.Modules.Announcements.Models import Announcement
    from tests._app import app as flask_app
    with flask_app.app_context():
        ann_id = _seed(message="zap")
    token = _login_superadmin(client)
    resp = client.delete(
        f"/api/v2/announcements/{ann_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 204
    with flask_app.app_context():
        assert Announcement.query.filter_by(id=ann_id).first() is None


def test_delete_404_when_missing(client):
    token = _login_superadmin(client)
    resp = client.delete(
        "/api/v2/announcements/9999999",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404


# ── Audit log integration ───────────────────────────────────


def test_create_records_audit_entry(client):
    """Every superadmin mutation must record_audit (CLAUDE.md
    invariant #7). Confirms the Controller calls it."""
    from api.Modules.Audit.Models import SuperadminAuditLog
    from tests._app import app as flask_app
    token = _login_superadmin(client)
    resp = client.post(
        "/api/v2/announcements",
        json={"message": "audited", "level": "info"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201
    with flask_app.app_context():
        rows = SuperadminAuditLog.query.filter_by(
            action="create_announcement",
        ).all()
        assert len(rows) >= 1


# ── Scheduled announcements (BACKLOG: scheduled banners) ────


def test_create_with_future_start_at_is_not_visible_yet(client):
    """A `start_at_iso` in the future schedules the banner — it
    persists with is_active=True but `is_visible` is False until
    the scheduled time arrives. Confirms the visibility helper
    (active_announcements) skips not-yet-started rows."""
    from datetime import datetime, timedelta, timezone
    future = (datetime.now(timezone.utc) + timedelta(hours=4)).isoformat()
    token = _login_superadmin(client)
    resp = client.post(
        "/api/v2/announcements",
        json={
            "message": "Scheduled maintenance Friday",
            "level": "warning",
            "start_at_iso": future,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201
    body = resp.get_json()
    a = body["announcement"]
    assert a["is_active"] is True
    assert a["is_visible"] is False


def test_create_with_past_start_at_is_visible_immediately(client):
    """A start_at in the past should still create the row and
    surface it as visible (the schedule has already arrived)."""
    from datetime import datetime, timedelta, timezone
    past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    token = _login_superadmin(client)
    resp = client.post(
        "/api/v2/announcements",
        json={
            "message": "Back-dated banner",
            "start_at_iso": past,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201
    a = resp.get_json()["announcement"]
    assert a["is_visible"] is True


def test_create_with_empty_start_at_starts_now(client):
    """Omitting / empty start_at_iso falls back to start-now —
    the legacy behaviour, preserved for callers that haven't
    been updated yet."""
    token = _login_superadmin(client)
    resp = client.post(
        "/api/v2/announcements",
        json={"message": "Hello", "start_at_iso": ""},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201
    a = resp.get_json()["announcement"]
    assert a["is_visible"] is True


def test_create_expires_days_measured_from_start_at(client):
    """A scheduled banner gets its full visibility window — expires
    `expires_days` days AFTER its start time, not from create."""
    from datetime import datetime, timedelta, timezone
    future = (datetime.now(timezone.utc) + timedelta(days=2))
    token = _login_superadmin(client)
    resp = client.post(
        "/api/v2/announcements",
        json={
            "message": "Future + expiring",
            "expires_days": 3,
            "start_at_iso": future.isoformat(),
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201
    a = resp.get_json()["announcement"]
    # expires_at is ISO; parse + verify it's ~5 days from now (2 + 3)
    exp = datetime.fromisoformat(a["expires_at"])
    diff_days = (exp - datetime.utcnow()).total_seconds() / 86400
    assert 4.9 < diff_days < 5.1


def test_create_bad_start_at_iso_falls_back_to_now(client):
    """Unparseable start_at_iso doesn't 422 — falls back to
    start-now so a typo can't block the announcement. (The
    superadmin can correct via delete + recreate.)"""
    token = _login_superadmin(client)
    resp = client.post(
        "/api/v2/announcements",
        json={"message": "Bad schedule", "start_at_iso": "not-a-date"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201
    a = resp.get_json()["announcement"]
    assert a["is_visible"] is True
