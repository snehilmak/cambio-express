"""HTTP integration tests for the Admin Controllers."""
from fastapi.testclient import TestClient


def _client():
    from api.main import api_app
    return TestClient(api_app)


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


# ── GET /admin/store-info ───────────────────────────────────


def test_get_store_info_returns_envelope(client, test_store_id):
    token = _login(client, test_store_id)
    resp = client.get(
        "/api/v2/admin/store-info",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert "store" in body
    assert body["store"]["id"] == test_store_id


def test_get_store_info_requires_jwt():
    resp = _client().get("/admin/store-info")
    assert resp.status_code == 401


def test_get_store_info_rejects_superadmin(client):
    login = client.post(
        "/api/v2/auth/login",
        json={
            "username": "superadmin",
            "password": "super2025!",
            "store_id": None,
        },
    )
    token = login.get_json()["access_token"]
    resp = client.get(
        "/api/v2/admin/store-info",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403


# ── PUT /admin/store-info ───────────────────────────────────


def test_put_store_info_updates_editable_fields(client, test_store_id):
    token = _login(client, test_store_id)
    resp = client.put(
        "/api/v2/admin/store-info",
        json={
            "name":             "Updated Store Name",
            "phone":            "555-1234",
            "address":          "123 Main St",
            "federal_tax_rate": 0.025,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    body = resp.get_json()["store"]
    assert body["name"]             == "Updated Store Name"
    assert body["phone"]            == "555-1234"
    assert body["address"]          == "123 Main St"
    assert body["federal_tax_rate"] == 0.025


def test_put_store_info_partial_update(client, test_store_id):
    """Only fields in the body land on the row; omitted fields
    are left alone."""
    token = _login(client, test_store_id)
    # Set a baseline first.
    client.put(
        "/api/v2/admin/store-info",
        json={"phone": "+1-555-AAAA"},
        headers={"Authorization": f"Bearer {token}"},
    )
    # Then PUT just `email` — phone must persist.
    resp = client.put(
        "/api/v2/admin/store-info",
        json={"email": "ops@example.com"},
        headers={"Authorization": f"Bearer {token}"},
    )
    body = resp.get_json()["store"]
    assert body["email"] == "ops@example.com"
    assert body["phone"] == "+1-555-AAAA"


def test_put_store_info_rejects_extra_fields(client, test_store_id):
    """Schema is extra=forbid — slug / plan / billing must not
    be writable here."""
    token = _login(client, test_store_id)
    resp = client.put(
        "/api/v2/admin/store-info",
        json={
            "name": "X",
            "slug": "totally-different-slug",  # not in schema
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422


def test_put_store_info_rejects_bad_tax_rate(client, test_store_id):
    """federal_tax_rate is bounded [0, 1] — reject 5%-as-5
    (operator should have entered 0.05)."""
    token = _login(client, test_store_id)
    resp = client.put(
        "/api/v2/admin/store-info",
        json={"federal_tax_rate": 5.0},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422


def test_put_store_info_requires_jwt():
    resp = _client().put(
        "/admin/store-info",
        json={"name": "X"},
    )
    assert resp.status_code == 401


def test_put_store_info_rejects_employee_role(client):
    """Cashier role can't update store info — only admin /
    owner / superadmin."""
    from app import User, db, app as flask_app
    with flask_app.app_context():
        u = User(
            store_id=None, username="employee_test_admin", role="employee",
            is_active=True,
        )
        u.set_password("emppass1234")
        db.session.add(u); db.session.commit()
    try:
        login = client.post(
            "/api/v2/auth/login",
            json={
                "username": "employee_test_admin",
                "password": "emppass1234",
                "store_id": None,
            },
        )
        token = login.get_json()["access_token"]
        resp = client.put(
            "/api/v2/admin/store-info",
            json={"name": "X"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 403
    finally:
        with flask_app.app_context():
            u2 = db.session.query(User).filter_by(
                username="employee_test_admin",
            ).first()
            if u2:
                db.session.delete(u2); db.session.commit()
