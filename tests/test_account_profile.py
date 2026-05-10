"""Personal `/account/profile` page — display name + email + phone +
timezone for any logged-in user, plus the read-only `last_login_at`
field that the login routes stamp on every successful sign-in.

Page rendering + form validation moved to React + the
`GET/PUT /api/v2/auth/profile` endpoints. SPA-side coverage lives
in tests/Modules/Auth/test_profile_endpoint.py. What's left here:

  - Legacy Flask /account/profile is now a 301 redirect, so
    every authed role can still link to it from chrome
  - Pure-function `_update_user_profile` validation still ships
    in app.py for the legacy /login fall-through and is exercised
    here as a smoke test
  - last_login_at stamping (login flow + helper)
  - Security page banner showing last sign-in
  - Topbar dropdown links + Security regression
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


# ── Flask redirect ─────────────────────────────────────────────


def test_anonymous_redirected(client):
    resp = client.get("/account/profile", follow_redirects=False)
    # Anonymous users get sent to /login by the login_required
    # decorator before the redirect to /app/account/profile fires.
    assert resp.status_code in (301, 302, 401)


def test_admin_legacy_url_redirects_to_app(logged_in_client):
    resp = logged_in_client.get(
        "/account/profile", follow_redirects=False,
    )
    assert resp.status_code == 301
    assert resp.headers["Location"] == "/app/account/profile"


def test_superadmin_legacy_url_redirects_to_app(client):
    """Every authed role gets the same 301 — profile is per-user,
    not per-role."""
    with client.application.app_context():
        sa_id = User.query.filter_by(username="superadmin").first().id
    sa = _client_for(client.application, sa_id, "superadmin", None)
    resp = sa.get("/account/profile", follow_redirects=False)
    assert resp.status_code == 301


def test_owner_legacy_url_redirects_to_app(client):
    with client.application.app_context():
        s = Store(name="OS", slug="os-prof", plan="basic")
        db.session.add(s); db.session.flush()
        sid = s.id
    own = _client_for(client.application,
                      _make_user(client.application, "owner", sid,
                                 username="own-prof@x.com"),
                      "owner", sid)
    resp = own.get("/account/profile", follow_redirects=False)
    assert resp.status_code == 301


def test_employee_legacy_url_redirects_to_app(client, test_store_id):
    emp = _client_for(client.application,
                      _make_user(client.application, "employee", test_store_id,
                                 username="emp-prof@test.com"),
                      "employee", test_store_id)
    resp = emp.get("/account/profile", follow_redirects=False)
    assert resp.status_code == 301


# ── Pure-function validator (still shipped in app.py) ─────────


def test_helper_returns_field_errors_directly():
    """Pure-function smoke: no DB, no session, just the validator.
    The legacy /login path still imports this helper, and the
    new SPA endpoint shares the same field-error contract."""
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


def test_record_login_helper_sets_timestamp(client):
    """Helper bumps last_login_at AND appends a LoginEvent row.
    Caller commits; the helper just stages the writes."""
    from app import User, LoginEvent, db
    with client.application.app_context():
        u = User.query.filter_by(role="superadmin").first()
        before = u.last_login_at
        _record_login(u, method="password")
        db.session.commit()
        u_after = db.session.get(User, u.id)
        assert u_after.last_login_at is not None
        assert u_after.last_login_at != before
        # LoginEvent row exists.
        assert LoginEvent.query.filter_by(
            user_id=u.id, method="password").count() >= 1


# Security page last-sign-in banner test removed: the page moved
# to React (/app/settings); the equivalent banner is now in the
# Profile page (read-only `last_login_at` field) which is covered
# by tests/Modules/Auth/test_profile_endpoint.py via the GET
# payload assertion.


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
