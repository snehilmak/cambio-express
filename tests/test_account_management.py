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
    """Employee login moved to /api/v2/auth/login (the SPA submits
    there scoped by store_id). The legacy /login/<slug> Flask form
    is now a 301 redirect — see test_legacy_login_slug_redirects."""
    sid = get_store_id()
    make_employee(client, sid)
    resp = client.post("/api/v2/auth/login", json={
        "username": "cashier",
        "password": "emppass123!",
        "store_id": sid,
    })
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["access_token"]
    assert body["role"] == "employee"
    assert body["store_id"] == sid


def test_employee_login_wrong_password(client):
    sid = get_store_id()
    make_employee(client, sid)
    resp = client.post("/api/v2/auth/login", json={
        "username": "cashier",
        "password": "wrongpassword",
        "store_id": sid,
    })
    assert resp.status_code == 401
    body = resp.get_json()
    assert "invalid" in str(body.get("detail", "")).lower()


def test_employee_login_unknown_slug_returns_404(client):
    """The slug lookup endpoint 404s for unknown slugs so the SPA
    can render an opaque "store not found" state."""
    resp = client.get("/api/v2/auth/store-by-slug/no-such-store")
    assert resp.status_code == 404


def test_employee_login_get_page_shows_store_context(client):
    """Slug lookup returns the store's display name so the SPA's
    branding pane reads correctly."""
    resp = client.get("/api/v2/auth/store-by-slug/test-store")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["name"] == "Test Store"
    assert body["slug"] == "test-store"


def test_legacy_login_slug_redirects_to_spa(client):
    """The legacy /login/<slug> URL stays live as a 301 to the
    React /app/login/<slug> page. Old PWAs / bookmarks keep
    working without a forced reset."""
    resp = client.get("/login/test-store", follow_redirects=False)
    assert resp.status_code == 301
    assert resp.headers["Location"] == "/app/login/test-store"


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
    """The /admin/settings hub moved to React (/app/settings); the
    legacy GET 301s. Page-rendering invariants moved to the SPA;
    here we just pin the redirect contract."""
    resp = logged_in_client.get("/admin/settings", follow_redirects=False)
    assert resp.status_code == 301
    assert resp.headers["Location"] == "/app/settings"


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
    # Create a second store with a different admin email. The legacy
    # /signup form was retired (redirects to /app/signup); we use the
    # FastAPI signup endpoint instead, same one the SPA submits to.
    r = client.post("/api/v2/auth/signup", json={
        "store_name": "Other Store",
        "email": "other@example.com",
        "password": "securepass1!",
        "phone": "",
    })
    assert r.status_code == 201, r.get_data(as_text=True)
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


# ── Task 4: Password change ─────────────────────────────────
#
# Form-based POST tests removed — /account/security now 301s to
# /app/settings, which submits to /api/v2/auth/change-password.
# The corresponding 4 validation tests + happy-path are exercised
# at the API level in tests/Modules/Auth/test_auth_controllers.py.


# ── Task 5: Team tab + employee password reset ───────────────





def test_team_reset_employee_password(logged_in_client):
    """The legacy flash text moved to React; assert on the password
    state directly. Form-handler 302s back to /admin/settings."""
    sid = get_store_id()
    emp_id = make_employee(logged_in_client, sid, username="resetme", password="oldpass123!")
    resp = logged_in_client.post(f"/admin/settings/team/{emp_id}", data={
        "password": "newpass456!",
        "confirm_password": "newpass456!"
    }, follow_redirects=False)
    assert resp.status_code in (302, 303)
    with flask_app.app_context():
        from app import User
        emp = db.session.get(User, emp_id)
        assert emp.check_password("newpass456!")
        assert not emp.check_password("oldpass123!")


def test_team_reset_scoped_to_store(logged_in_client, client):
    # Create a second store and its employee. Legacy /signup is now
    # a redirect; use the FastAPI signup endpoint instead.
    r = client.post("/api/v2/auth/signup", json={
        "store_name": "Other Store",
        "email": "other2@example.com",
        "password": "securepass1!",
        "phone": "",
    })
    assert r.status_code == 201, r.get_data(as_text=True)
    with flask_app.app_context():
        from app import Store, User
        other_store = Store.query.filter_by(email="other2@example.com").first()
        other_emp = User(store_id=other_store.id, username="otherworker",
                         full_name="Other Worker", role="employee")
        other_emp.set_password("original123!")
        db.session.add(other_emp)
        db.session.commit()
        other_emp_id = other_emp.id

    resp = logged_in_client.post(f"/admin/settings/team/{other_emp_id}", data={
        "password": "hacked123!!",
        "confirm_password": "hacked123!!"
    })
    # Should 404 because user is not in this admin's store
    assert resp.status_code == 404
    with flask_app.app_context():
        from app import User
        emp = db.session.get(User, other_emp_id)
        assert emp.check_password("original123!")


def test_team_reset_password_too_short(logged_in_client):
    sid = get_store_id()
    emp_id = make_employee(logged_in_client, sid, username="shortpw")
    resp = logged_in_client.post(f"/admin/settings/team/{emp_id}", data={
        "password": "short",
        "confirm_password": "short"
    }, follow_redirects=True)
    assert resp.status_code == 200
    assert b"8" in resp.data


def test_team_reset_passwords_do_not_match(logged_in_client):
    """Mismatched passwords short-circuit the reset. The legacy
    flash-text confirmation moved to React; assert the no-op
    on the user row instead of looking for the string."""
    from app import User
    sid = get_store_id()
    emp_id = make_employee(logged_in_client, sid, username="mismatch")
    with flask_app.app_context():
        old_hash = User.query.filter_by(id=emp_id).first().password_hash
    resp = logged_in_client.post(f"/admin/settings/team/{emp_id}", data={
        "password": "newpass123!",
        "confirm_password": "different123!"
    }, follow_redirects=False)
    assert resp.status_code in (302, 303)
    with flask_app.app_context():
        # Password hash unchanged on mismatch.
        assert User.query.filter_by(id=emp_id).first().password_hash == old_hash
