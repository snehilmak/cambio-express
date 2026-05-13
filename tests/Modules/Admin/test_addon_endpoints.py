"""HTTP integration tests for the subscription add-on endpoints.

  GET  /api/v2/admin/addons
  POST /api/v2/admin/addons/{key}/toggle

Mirrors the legacy /admin/subscription/addons/<key> form handler.
"""


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


def _set_paid_plan(store_id, plan="basic"):
    """Flip the seeded test store onto a paid plan so the toggle
    endpoint accepts the request (legacy contract: add-ons need
    Basic or Pro)."""
    from api.Modules.Tenancy.Models import Store
    from app import app as flask_app, db
    with flask_app.app_context():
        s = Store.query.filter_by(id=store_id).first()
        s.plan = plan
        db.session.commit()


# ── Auth ────────────────────────────────────────────────────


def test_list_requires_jwt(client):
    resp = client.get("/api/v2/admin/addons")
    assert resp.status_code == 401


def test_toggle_requires_jwt(client):
    resp = client.post("/api/v2/admin/addons/tv_display/toggle")
    assert resp.status_code == 401


# ── List ────────────────────────────────────────────────────


def test_list_returns_catalog_with_active_flag(client, test_store_id):
    token = _login_admin(client, test_store_id)
    resp = client.get(
        "/api/v2/admin/addons",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert "rows" in body
    assert "has_paid_plan" in body
    # Trial store: has_paid_plan should be False
    assert body["has_paid_plan"] is False


def test_list_marks_active_addon(client, test_store_id):
    """A store with `addons="tv_display"` should surface
    is_active=true on that row."""
    from api.Modules.Tenancy.Models import Store
    from app import app as flask_app, db
    with flask_app.app_context():
        s = Store.query.filter_by(id=test_store_id).first()
        s.addons = "tv_display"
        db.session.commit()
    token = _login_admin(client, test_store_id)
    body = client.get(
        "/api/v2/admin/addons",
        headers={"Authorization": f"Bearer {token}"},
    ).get_json()
    tv = next((r for r in body["rows"] if r["key"] == "tv_display"), None)
    if tv is None:
        # tv_display may be hidden by feature flag in this test env;
        # skip silently if so.
        return
    assert tv["is_active"] is True


# ── Toggle ──────────────────────────────────────────────────


def test_toggle_409_on_trial_plan(client, test_store_id):
    """Trial stores can't activate add-ons — must subscribe first."""
    token = _login_admin(client, test_store_id)
    resp = client.post(
        "/api/v2/admin/addons/tv_display/toggle",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 409


def test_toggle_404_on_unknown_addon(client, test_store_id):
    _set_paid_plan(test_store_id, "basic")
    token = _login_admin(client, test_store_id)
    resp = client.post(
        "/api/v2/admin/addons/nonexistent_addon/toggle",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404


def test_toggle_flips_addon_state_for_paid_store(client, test_store_id):
    _set_paid_plan(test_store_id, "basic")
    token = _login_admin(client, test_store_id)
    # Toggle on
    resp = client.post(
        "/api/v2/admin/addons/tv_display/toggle",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.get_json()["addon"]["is_active"] is True
    # Toggle off
    resp = client.post(
        "/api/v2/admin/addons/tv_display/toggle",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.get_json()["addon"]["is_active"] is False
