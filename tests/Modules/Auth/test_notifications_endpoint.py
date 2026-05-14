"""HTTP integration tests for the account-notifications endpoints.

Powers /app/account/notifications. GET returns the user's two
boolean prefs + a `trial_toggle_applies` flag the SPA uses to
render the trial-reminder toggle as interactive vs informational.
PUT applies changes; both fields are optional.
"""
from tests._app import db


def _login(client_, store_id):
    resp = client_.post(
        "/api/v2/auth/login",
        json={
            "username": "admin@test.com",
            "password": "testpass123!",
            "store_id": store_id,
        },
    )
    return resp.get_json()["access_token"]


# ── auth gating ─────────────────────────────────────────────


def test_notifications_requires_jwt(client):
    resp = client.get("/api/v2/auth/notifications")
    assert resp.status_code == 401


# ── GET /auth/notifications ─────────────────────────────────


def test_notifications_returns_default_prefs(client, test_store_id):
    """Fresh seeded admin: trial reminders default ON (we want
    operators to know their trial is ending), announcements
    default OFF (opt-in)."""
    token = _login(client, test_store_id)
    body = client.get(
        "/api/v2/auth/notifications",
        headers={"Authorization": f"Bearer {token}"},
    ).get_json()
    assert body["notify_trial_reminders"] is True
    assert body["notify_announcement_email"] is False
    assert body["role"] == "admin"
    # Test fixture seeds the store on `trial`, so admin sees the
    # toggle as interactive.
    assert body["trial_toggle_applies"] is True


def test_notifications_trial_toggle_off_for_paid_store(
    client, test_store_id,
):
    """Admin on a paid plan: trial reminder is informational
    (toggle is shown disabled in the SPA)."""
    from api.Modules.Tenancy.Models import Store
    from tests._app import app as flask_app, db
    with flask_app.app_context():
        s = db.session.get(Store, test_store_id)
        s.plan = "basic"
        db.session.commit()
    token = _login(client, test_store_id)
    body = client.get(
        "/api/v2/auth/notifications",
        headers={"Authorization": f"Bearer {token}"},
    ).get_json()
    assert body["trial_toggle_applies"] is False


def test_notifications_trial_toggle_off_for_employee(
    client, test_store_id,
):
    """Employees don't own a trial — toggle never applies."""
    from api.Modules.Tenancy.Models import User
    from tests._app import app as flask_app, db
    with flask_app.app_context():
        u = User(
            store_id=test_store_id, username="cashier-pref@x.com",
            full_name="Cashier", role="employee",
        )
        u.set_password("p")
        db.session.add(u); db.session.commit()
        uid = u.id
    # Issue a JWT directly — the API login path rejects employees
    # via cross-store, so we mint the token from the issuer.
    from tests._app import app as flask_app
    with flask_app.app_context():
        from api.Modules.Auth.Services.jwt_issuer import (
            JWTIssuer, issue_access_token,
        )
        from api.Modules.Auth.Services import permissions_for
        token = issue_access_token(JWTIssuer(
            sub=uid, role="employee", store_id=test_store_id,
            permissions=permissions_for("employee"),
            full_name="Cashier", username="cashier-pref@x.com",
        ))
    body = client.get(
        "/api/v2/auth/notifications",
        headers={"Authorization": f"Bearer {token}"},
    ).get_json()
    assert body["trial_toggle_applies"] is False
    assert body["role"] == "employee"


# ── PUT /auth/notifications ─────────────────────────────────


def test_notifications_update_persists_trial_pref(
    client, test_store_id,
):
    """Trial pref defaults True; flip it off via PUT and confirm
    persistence."""
    from api.Modules.Tenancy.Models import User
    from tests._app import app as flask_app
    token = _login(client, test_store_id)
    body = client.put(
        "/api/v2/auth/notifications",
        json={"notify_trial_reminders": False},
        headers={"Authorization": f"Bearer {token}"},
    ).get_json()
    assert body["notify_trial_reminders"] is False
    with flask_app.app_context():
        u = db.session.query(User).filter_by(username="admin@test.com").first()
        assert u.notify_trial_reminders is False
        # Untouched field stays at its prior value.
        assert u.notify_announcement_email is False


def test_notifications_update_persists_announcement_pref(
    client, test_store_id,
):
    from api.Modules.Tenancy.Models import User
    from tests._app import app as flask_app
    token = _login(client, test_store_id)
    body = client.put(
        "/api/v2/auth/notifications",
        json={"notify_announcement_email": True},
        headers={"Authorization": f"Bearer {token}"},
    ).get_json()
    assert body["notify_announcement_email"] is True
    with flask_app.app_context():
        u = db.session.query(User).filter_by(username="admin@test.com").first()
        assert u.notify_announcement_email is True


def test_notifications_update_can_toggle_off(client, test_store_id):
    """Off → On → Off round-trip — the JSON `false` must take
    effect (not be confused with `None`/missing)."""
    token = _login(client, test_store_id)
    client.put(
        "/api/v2/auth/notifications",
        json={"notify_trial_reminders": True},
        headers={"Authorization": f"Bearer {token}"},
    )
    body = client.put(
        "/api/v2/auth/notifications",
        json={"notify_trial_reminders": False},
        headers={"Authorization": f"Bearer {token}"},
    ).get_json()
    assert body["notify_trial_reminders"] is False


def test_notifications_update_partial_leaves_others_alone(
    client, test_store_id,
):
    """Updating one pref doesn't reset the other."""
    from api.Modules.Tenancy.Models import User
    from tests._app import app as flask_app
    token = _login(client, test_store_id)
    # Set both first.
    client.put(
        "/api/v2/auth/notifications",
        json={
            "notify_trial_reminders": True,
            "notify_announcement_email": True,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    # Toggle only the announcement pref.
    body = client.put(
        "/api/v2/auth/notifications",
        json={"notify_announcement_email": False},
        headers={"Authorization": f"Bearer {token}"},
    ).get_json()
    # Trial pref is untouched.
    assert body["notify_trial_reminders"] is True
    assert body["notify_announcement_email"] is False
    with flask_app.app_context():
        u = db.session.query(User).filter_by(username="admin@test.com").first()
        assert u.notify_trial_reminders is True
        assert u.notify_announcement_email is False


def test_notifications_update_empty_body_is_noop(
    client, test_store_id,
):
    """An empty PUT is valid — returns current state. Useful if
    the SPA wants to round-trip values through the controller
    without changing any field."""
    token = _login(client, test_store_id)
    resp = client.put(
        "/api/v2/auth/notifications",
        json={},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert "notify_trial_reminders" in body
    assert "notify_announcement_email" in body


def test_notifications_update_rejects_extra_fields(
    client, test_store_id,
):
    """Pydantic schema is extra="forbid" — typos must 422."""
    token = _login(client, test_store_id)
    resp = client.put(
        "/api/v2/auth/notifications",
        json={"notify_extra_email": True},  # not a real field
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422


# ── Flask redirect ──────────────────────────────────────────


def test_legacy_account_notifications_redirects_to_app(
    logged_in_client,
):
    resp = logged_in_client.get(
        "/account/notifications", follow_redirects=False,
    )
    assert resp.status_code == 301
    assert resp.headers["Location"] == "/app/account/notifications"
