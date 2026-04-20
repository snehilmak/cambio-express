import pytest
from app import app as flask_app, db


def make_employee(client, store_id, username="cashier", password="emppass123!"):
    """Helper: create an employee for the given store_id."""
    with flask_app.app_context():
        from app import User
        e = User(store_id=store_id, username=username,
                 full_name="Test Cashier", role="employee")
        e.set_password(password)
        db.session.add(e)
        db.session.commit()
        return e.id


def get_store_id(slug="test-store"):
    with flask_app.app_context():
        from app import Store
        return Store.query.filter_by(slug=slug).first().id


# ── Task 1: /login/<slug> ─────────────────────────────────────

def test_employee_login_with_valid_credentials(client):
    sid = get_store_id()
    make_employee(client, sid)
    resp = client.post("/login/test-store", data={
        "username": "cashier",
        "password": "emppass123!"
    }, follow_redirects=False)
    assert resp.status_code == 302
    assert "dashboard" in resp.headers["Location"]


def test_employee_login_wrong_password(client):
    sid = get_store_id()
    make_employee(client, sid)
    resp = client.post("/login/test-store", data={
        "username": "cashier",
        "password": "wrongpassword"
    })
    assert resp.status_code == 200
    assert b"Invalid username or password" in resp.data


def test_employee_login_unknown_slug_returns_404(client):
    resp = client.get("/login/no-such-store")
    assert resp.status_code == 404


def test_employee_login_get_page_shows_store_context(client):
    resp = client.get("/login/test-store")
    assert resp.status_code == 200
    assert b"Test Store" in resp.data or b"test-store" in resp.data


# ── Task 2: main /login restricted to admin/superadmin ───────

def test_employee_blocked_on_main_login(client):
    sid = get_store_id()
    make_employee(client, sid, username="blockeduser", password="emppass123!")
    resp = client.post("/login", data={
        "username": "blockeduser",
        "password": "emppass123!"
    })
    assert resp.status_code == 200
    assert b"store" in resp.data.lower()
    # must NOT have set session (not redirected to dashboard)
    with client.session_transaction() as sess:
        assert "user_id" not in sess


def test_admin_can_still_use_main_login(client):
    resp = client.post("/login", data={
        "username": "admin@test.com",
        "password": "testpass123!"
    }, follow_redirects=False)
    assert resp.status_code == 302
    assert "dashboard" in resp.headers["Location"]


# ── Task 3: /admin/settings — Store Info tab ─────────────────

def test_settings_page_loads(logged_in_client):
    resp = logged_in_client.get("/admin/settings")
    assert resp.status_code == 200
    assert b"Settings" in resp.data
    assert b"Store Info" in resp.data


def test_settings_store_info_updates_store(logged_in_client):
    resp = logged_in_client.post("/admin/settings", data={
        "_tab": "store",
        "store_name": "Updated Store Name",
        "email": "updated@test.com",
        "phone": "555-9999"
    }, follow_redirects=True)
    assert resp.status_code == 200
    with flask_app.app_context():
        from app import Store
        s = Store.query.filter_by(slug="test-store").first()
        assert s.name == "Updated Store Name"
        assert s.email == "updated@test.com"
        assert s.phone == "555-9999"


def test_settings_store_info_updates_admin_username(logged_in_client):
    logged_in_client.post("/admin/settings", data={
        "_tab": "store",
        "store_name": "Test Store",
        "email": "newemail@test.com",
        "phone": ""
    }, follow_redirects=True)
    with flask_app.app_context():
        from app import User
        u = User.query.filter_by(username="newemail@test.com").first()
        assert u is not None
        assert u.role == "admin"


def test_settings_store_info_rejects_blank_name(logged_in_client):
    resp = logged_in_client.post("/admin/settings", data={
        "_tab": "store",
        "store_name": "",
        "email": "admin@test.com",
        "phone": ""
    })
    assert resp.status_code == 200
    assert b"required" in resp.data.lower() or b"name" in resp.data.lower()
    with flask_app.app_context():
        from app import Store
        s = Store.query.filter_by(slug="test-store").first()
        assert s.name == "Test Store"  # unchanged


def test_settings_store_info_rejects_duplicate_email(logged_in_client, client):
    # Create a second store with a different admin email
    client.post("/signup", data={
        "store_name": "Other Store",
        "email": "other@example.com",
        "password": "securepass1!",
        "phone": ""
    })
    resp = logged_in_client.post("/admin/settings", data={
        "_tab": "store",
        "store_name": "Test Store",
        "email": "other@example.com",
        "phone": ""
    })
    assert resp.status_code == 200
    assert b"already registered" in resp.data.lower() or b"already" in resp.data.lower()
    with flask_app.app_context():
        from app import Store
        s = Store.query.filter_by(slug="test-store").first()
        assert s.email == "admin@test.com"  # unchanged
