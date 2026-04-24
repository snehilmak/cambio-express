"""Personal `/account/profile` page — display name + email + phone +
timezone for any logged-in user, plus the read-only `last_login_at`
field that the login routes stamp on every successful sign-in.

Mirrors the cross-role coverage of test_account_security.py. The
helper logic (_update_user_profile) is exercised through the route so
the validation messages we assert here are the same strings users see.
"""
from datetime import datetime, timedelta
from app import db, User, Store, _update_user_profile, _record_login


def _make_user(app, role, store_id, *, username, password="x", full_name="X"):
    with app.app_context():
        u = User(store_id=store_id, username=username, full_name=full_name, role=role)
        u.set_password(password)
        db.session.add(u); db.session.commit()
        return u.id


def _client_for(app, user_id, role, store_id):
    c = app.test_client()
    with c.session_transaction() as s:
        s["user_id"] = user_id
        s["role"] = role
        s["store_id"] = store_id
    return c


# ── Access control ─────────────────────────────────────────────

def test_anonymous_redirected(client):
    resp = client.get("/account/profile")
    assert resp.status_code in (302, 401)


def test_admin_can_open_profile(logged_in_client):
    resp = logged_in_client.get("/account/profile")
    assert resp.status_code == 200
    body = resp.data.decode()
    for token in ("Personal info", "Display name", "Email", "Phone",
                  "Timezone", "Member since", "Last sign-in"):
        assert token in body, f"missing field: {token}"


def test_superadmin_can_open_profile(client):
    with client.application.app_context():
        sa_id = User.query.filter_by(username="superadmin").first().id
    sa = _client_for(client.application, sa_id, "superadmin", None)
    assert sa.get("/account/profile").status_code == 200


def test_owner_can_open_profile(client):
    with client.application.app_context():
        s = Store(name="OS", slug="os-prof", plan="basic")
        db.session.add(s); db.session.flush()
        sid = s.id
    own = _client_for(client.application,
                      _make_user(client.application, "owner", sid,
                                 username="own-prof@x.com"),
                      "owner", sid)
    assert own.get("/account/profile").status_code == 200


def test_employee_can_open_profile(client, test_store_id):
    emp = _client_for(client.application,
                      _make_user(client.application, "employee", test_store_id,
                                 username="emp-prof@test.com"),
                      "employee", test_store_id)
    assert emp.get("/account/profile").status_code == 200


# ── Save round-trip ────────────────────────────────────────────

def test_full_profile_save_round_trip(logged_in_client, test_admin_id):
    """All four fields populated; phone gets normalized (whitespace +
    parens + hyphens stripped); email gets lowercased; timezone is
    stored verbatim. Server side persists what we sent."""
    resp = logged_in_client.post("/account/profile", data={
        "full_name": "New Name",
        "email":     "Mixed.Case@EXAMPLE.com",
        "phone":     "+1 (555) 987-6543",
        "timezone":  "America/Chicago",
    }, follow_redirects=True)
    assert resp.status_code == 200
    with logged_in_client.application.app_context():
        u = db.session.get(User, test_admin_id)
        assert u.full_name == "New Name"
        assert u.email == "mixed.case@example.com"
        assert u.phone == "+15559876543"
        assert u.timezone == "America/Chicago"


def test_optional_fields_can_be_cleared(logged_in_client, test_admin_id):
    """Email / phone / timezone are nullable — submitting blanks
    clears them. Display name remains required."""
    # Set them first
    logged_in_client.post("/account/profile", data={
        "full_name": "X", "email": "x@y.com", "phone": "+15550000000",
        "timezone": "UTC",
    })
    # Clear them
    logged_in_client.post("/account/profile", data={
        "full_name": "X", "email": "", "phone": "", "timezone": "",
    })
    with logged_in_client.application.app_context():
        u = db.session.get(User, test_admin_id)
        assert u.email == ""
        assert u.phone == ""
        assert u.timezone == ""


# ── Validation ─────────────────────────────────────────────────

def test_blank_display_name_rejected(logged_in_client):
    resp = logged_in_client.post("/account/profile", data={
        "full_name": "  ", "email": "", "phone": "", "timezone": "",
    })
    assert resp.status_code == 200
    assert b"cannot be empty" in resp.data.lower()


def test_invalid_email_rejected(logged_in_client):
    resp = logged_in_client.post("/account/profile", data={
        "full_name": "X", "email": "not-an-email", "phone": "", "timezone": "",
    })
    assert resp.status_code == 200
    assert b"valid email" in resp.data.lower()


def test_invalid_phone_rejected(logged_in_client):
    resp = logged_in_client.post("/account/profile", data={
        "full_name": "X", "email": "", "phone": "abc-def", "timezone": "",
    })
    assert resp.status_code == 200
    assert b"valid phone" in resp.data.lower()


def test_unknown_timezone_rejected(logged_in_client):
    """Curated zone list — anything off the list is rejected so we
    don't end up with random IANA strings nobody renders correctly."""
    resp = logged_in_client.post("/account/profile", data={
        "full_name": "X", "email": "", "phone": "", "timezone": "Mars/Phobos",
    })
    assert resp.status_code == 200
    assert b"pick a timezone" in resp.data.lower()


def test_helper_returns_field_errors_directly():
    """Pure-function smoke: no DB, no session, just the validator."""
    class U: pass
    errs = _update_user_profile(U(), "", "x", "", "")
    assert "full_name" in errs
    errs = _update_user_profile(U(), "ok", "x@", "", "")
    assert "email" in errs
    errs = _update_user_profile(U(), "ok", "", "abc", "")
    assert "phone" in errs
    errs = _update_user_profile(U(), "ok", "", "", "Atlantis/Lost")
    assert "timezone" in errs


# ── last_login_at stamping ─────────────────────────────────────

def test_password_login_stamps_last_login_at(client, test_admin_id):
    """Password sign-in via /login → last_login_at is set + commits.
    Sanity: it was None on the seeded fixture."""
    with client.application.app_context():
        u = db.session.get(User, test_admin_id)
        assert u.last_login_at is None  # baseline
    resp = client.post("/login", data={
        "username": "admin@test.com", "password": "testpass123!",
    }, follow_redirects=False)
    assert resp.status_code == 302
    with client.application.app_context():
        u = db.session.get(User, test_admin_id)
        assert u.last_login_at is not None
        # Stamped within the last few seconds
        assert (datetime.utcnow() - u.last_login_at) < timedelta(seconds=10)


def test_record_login_helper_sets_timestamp():
    """Pure-function helper — no commit, just mutation."""
    class U:
        last_login_at = None
    u = U()
    _record_login(u)
    assert u.last_login_at is not None


def test_security_page_shows_last_sign_in_banner(client, test_admin_id):
    """When last_login_at is set, the Security page surfaces it as a
    'we noticed you signed in at X' banner."""
    with client.application.app_context():
        u = db.session.get(User, test_admin_id)
        u.last_login_at = datetime(2025, 1, 15, 10, 30, 0)
        sid = u.store_id
        db.session.commit()
    c = _client_for(client.application, test_admin_id, "admin", sid)
    body = c.get("/account/security").data.decode()
    assert "Last sign-in" in body
    assert "Jan 15, 2025" in body


# ── Topbar dropdown wiring ─────────────────────────────────────

def test_topbar_dropdown_links_profile_for_admin_chrome(logged_in_client):
    body = logged_in_client.get("/admin/settings?tab=store").data.decode()
    assert "/account/profile" in body


def test_topbar_dropdown_links_profile_for_owner_chrome(client):
    with client.application.app_context():
        s = Store(name="OS", slug="os-prof2", plan="basic")
        db.session.add(s); db.session.flush()
        sid = s.id
    own = _client_for(client.application,
                      _make_user(client.application, "owner", sid,
                                 username="own-prof2@x.com"),
                      "owner", sid)
    body = own.get("/owner/dashboard").data.decode()
    assert "/account/profile" in body


# ── Negative regression ────────────────────────────────────────

def test_security_page_no_longer_owns_display_name(logged_in_client):
    """Display name moved off Security to Profile — make sure the
    Security page doesn't accidentally still render the input."""
    body = logged_in_client.get("/account/security").data.decode()
    # The Profile page input is `name="full_name"`; Security shouldn't
    # have an editable display-name form anymore.
    assert 'name="full_name"' not in body
