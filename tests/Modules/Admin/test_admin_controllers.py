"""HTTP integration tests for the Admin Controllers."""
from fastapi.testclient import TestClient
from tests._app import db, db_session
import pytest


@pytest.fixture
def api_client():
    from api.main import api_app
    with TestClient(api_app) as c:
        yield c


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


def test_get_store_info_requires_jwt(client):
    """Routes through the Flask dispatcher (same path as prod
    SPA) to avoid leaking FastAPI TestClient asyncio tasks on
    Python 3.12."""
    resp = client.get("/api/v2/admin/store-info")
    assert resp.status_code == 401


def test_get_store_info_rejects_superadmin(client):
    from tests.conftest import login_superadmin
    token = login_superadmin(client)
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


def test_put_store_info_requires_jwt(client):
    """Routes through the Flask dispatcher (same path as prod
    SPA) to avoid leaking FastAPI TestClient asyncio tasks on
    Python 3.12."""
    resp = client.put(
        "/api/v2/admin/store-info",
        json={"name": "X"},
    )
    assert resp.status_code == 401


def test_put_store_info_rejects_employee_role(client):
    """Cashier role can't update store info — only admin /
    owner / superadmin."""
    from api.Modules.Tenancy.Models import User
    from tests._app import db
    with db_session():
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
        with db_session():
            u2 = db.session.query(User).filter_by(
                username="employee_test_admin",
            ).first()
            if u2:
                db.session.delete(u2); db.session.commit()


# ── GET/POST/PUT/DELETE /admin/team ─────────────────────────


def test_team_list_returns_envelope(client, test_store_id):
    token = _login(client, test_store_id)
    resp = client.get(
        "/api/v2/admin/team",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert "members" in body


def test_team_create_then_list(client, test_store_id):
    token = _login(client, test_store_id)
    create = client.post(
        "/api/v2/admin/team",
        json={"name": "Maria"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert create.status_code == 201, create.get_data(as_text=True)
    new_id = create.get_json()["id"]
    listed = client.get(
        "/api/v2/admin/team",
        headers={"Authorization": f"Bearer {token}"},
    )
    members = listed.get_json()["members"]
    assert any(m["id"] == new_id and m["is_active"] for m in members)


def test_team_update_renames_and_deactivates(client, test_store_id):
    token = _login(client, test_store_id)
    create = client.post(
        "/api/v2/admin/team",
        json={"name": "Bob"},
        headers={"Authorization": f"Bearer {token}"},
    )
    eid = create.get_json()["id"]

    rename = client.put(
        f"/api/v2/admin/team/{eid}",
        json={"name": "Robert"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert rename.status_code == 200
    assert rename.get_json()["name"] == "Robert"

    flip = client.put(
        f"/api/v2/admin/team/{eid}",
        json={"is_active": False},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert flip.status_code == 200
    assert flip.get_json()["is_active"] is False


def test_team_delete_soft_deletes(client, test_store_id):
    """DELETE flips is_active=False; the row stays so historical
    employee_name attribution on past Transfer rows survives."""
    token = _login(client, test_store_id)
    create = client.post(
        "/api/v2/admin/team",
        json={"name": "TempCashier"},
        headers={"Authorization": f"Bearer {token}"},
    )
    eid = create.get_json()["id"]
    delete = client.delete(
        f"/api/v2/admin/team/{eid}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert delete.status_code == 204
    listed = client.get(
        "/api/v2/admin/team",
        headers={"Authorization": f"Bearer {token}"},
    )
    found = next(
        m for m in listed.get_json()["members"] if m["id"] == eid
    )
    # Row still present, but inactive — soft-delete contract.
    assert found["is_active"] is False


def test_team_create_rejects_blank_name(client, test_store_id):
    token = _login(client, test_store_id)
    resp = client.post(
        "/api/v2/admin/team",
        json={"name": "   "},
        headers={"Authorization": f"Bearer {token}"},
    )
    # Pydantic rejects min_length=1 on stripped, OR Service raises
    # 422 — either way it must not 201.
    assert resp.status_code in (422,)


def test_team_update_404_for_cross_tenant(client, test_store_id):
    token = _login(client, test_store_id)
    resp = client.put(
        "/api/v2/admin/team/99999",
        json={"name": "Nope"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404


def test_team_endpoints_require_admin_role(client):
    """Cashier role can't manage roster."""
    from api.Modules.Tenancy.Models import User
    from tests._app import db
    with db_session():
        u = User(
            store_id=None, username="employee_team_admin",
            role="employee", is_active=True,
        )
        u.set_password("emppass1234")
        db.session.add(u); db.session.commit()
    try:
        login = client.post(
            "/api/v2/auth/login",
            json={
                "username": "employee_team_admin",
                "password": "emppass1234",
                "store_id": None,
            },
        )
        token = login.get_json()["access_token"]
        c = client.post(
            "/api/v2/admin/team",
            json={"name": "X"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert c.status_code == 403
    finally:
        with db_session():
            u2 = db.session.query(User).filter_by(
                username="employee_team_admin",
            ).first()
            if u2:
                db.session.delete(u2); db.session.commit()


def test_team_endpoints_require_jwt(client):
    """All four verbs reject unauthed callers. Routes through
    the Flask dispatcher (the same path the SPA uses in prod) —
    avoids creating bare FastAPI TestClient instances that leak
    asyncio tasks on Python 3.12 + tip the cumulative-leak
    threshold that causes test_unlock_404_when_no_report's
    setup to fail."""
    g = client.get("/api/v2/admin/team")
    p = client.post("/api/v2/admin/team", json={"name": "X"})
    u = client.put("/api/v2/admin/team/1", json={"name": "X"})
    d = client.delete("/api/v2/admin/team/1")
    assert g.status_code == 401
    assert p.status_code == 401
    assert u.status_code == 401
    assert d.status_code == 401


# ── Receipt-customization fields ────────────────────────────


def test_get_store_info_includes_receipt_fields_defaults(
    client, test_store_id,
):
    """A store that's never customized its receipt branding gets
    empty strings for the three receipt_* fields — the SPA
    settings form renders empty inputs in that state."""
    token = _login(client, test_store_id)
    body = client.get(
        "/api/v2/admin/store-info",
        headers={"Authorization": f"Bearer {token}"},
    ).get_json()["store"]
    assert "receipt_logo_url" in body
    assert "receipt_footer" in body
    assert "receipt_tax_id" in body
    assert body["receipt_logo_url"] == ""
    assert body["receipt_footer"] == ""
    assert body["receipt_tax_id"] == ""


def test_put_store_info_persists_receipt_customization(
    client, test_store_id,
):
    """All three receipt_* fields round-trip from PUT body →
    DB → next GET. They're set / cleared independently of the
    other Store fields."""
    from api.Modules.Tenancy.Models import Store
    token = _login(client, test_store_id)
    resp = client.put(
        "/api/v2/admin/store-info",
        json={
            "receipt_logo_url": "https://cdn.example.com/logo.png",
            "receipt_footer": "Refunds within 30 days with the receipt.",
            "receipt_tax_id": "EIN 12-3456789",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, resp.get_data(as_text=True)
    body = resp.get_json()["store"]
    assert body["receipt_logo_url"] == "https://cdn.example.com/logo.png"
    assert body["receipt_footer"] == "Refunds within 30 days with the receipt."
    assert body["receipt_tax_id"] == "EIN 12-3456789"
    with db_session():
        s = db.session.get(Store, test_store_id)
        assert s.receipt_logo_url == "https://cdn.example.com/logo.png"
        assert s.receipt_footer == "Refunds within 30 days with the receipt."
        assert s.receipt_tax_id == "EIN 12-3456789"


def test_put_store_info_clears_receipt_field_with_empty_string(
    client, test_store_id,
):
    """Passing ``""`` wipes the field back to the default layout
    — the SPA UI relies on this to let an operator turn off the
    custom footer without nulling the column."""
    from api.Modules.Tenancy.Models import Store
    token = _login(client, test_store_id)
    # First set it.
    client.put(
        "/api/v2/admin/store-info",
        json={"receipt_footer": "Custom message"},
        headers={"Authorization": f"Bearer {token}"},
    )
    # Now clear it.
    resp = client.put(
        "/api/v2/admin/store-info",
        json={"receipt_footer": ""},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.get_json()["store"]["receipt_footer"] == ""
    with db_session():
        s = db.session.get(Store, test_store_id)
        assert s.receipt_footer == ""


def test_put_store_info_rejects_oversized_receipt_field(
    client, test_store_id,
):
    """Pydantic max_length is the boundary check — 500 chars is
    the column width. Anything bigger gets 422 instead of crashing
    on the INSERT."""
    token = _login(client, test_store_id)
    resp = client.put(
        "/api/v2/admin/store-info",
        json={"receipt_footer": "x" * 501},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422


def test_put_store_info_rejects_employee_role(client, test_store_id):
    """Cashiers (role=employee) can't edit store info — the
    role gate applies to every editable field, including the new
    receipt customization ones."""
    from api.Modules.Tenancy.Models import User
    with db_session():
        emp = User(
            store_id=test_store_id,
            username="receipt_emp@test.com",
            full_name="Receipt Emp",
            role="employee",
        )
        emp.set_password("p123pass!")
        db.session.add(emp); db.session.commit()
    login = client.post(
        "/api/v2/auth/login",
        json={
            "username": "receipt_emp@test.com",
            "password": "p123pass!",
            "store_id": test_store_id,
        },
    )
    token = login.get_json()["access_token"]
    resp = client.put(
        "/api/v2/admin/store-info",
        json={"receipt_footer": "Cashier shouldn't write this"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403
