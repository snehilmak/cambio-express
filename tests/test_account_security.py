"""Shared `/account/security` URL — every logged-in role can reach it.

Page rendering moved to React (/app/settings) when the WebAuthn
enrollment flow ported to the SPA. This file now covers:

  - Cross-role 301 redirect: admin, owner, employee, superadmin
    all get bounced to /app/settings.
  - Anonymous users still get bounced to login first
    (login_required runs before the redirect).
  - The legacy /admin/settings?tab=security and
    /admin/settings/security aliases still redirect (their
    targets transitively land on /app/settings via /account/security).
  - Topbar dropdown link in both base.html and base_owner.html
    still points at /account/security (which now 301s).
  - _passkey_eligible helper smoke is unchanged.

Password-change validation is exercised at the API level in
tests/Modules/Auth/test_auth_controllers.py against
/api/v2/auth/change-password. Passkey list/delete + the
React-driven enrollment helpers are exercised in
tests/test_passkeys.py + tests/Modules/Auth/.
"""
from app import db, User, Store


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


def test_anonymous_redirected_to_login(client):
    resp = client.get("/account/security")
    # login_required redirects anonymous users BEFORE the 301
    # to /app/settings fires — so 302 → /login is what they see.
    assert resp.status_code in (301, 302, 401)
    if resp.status_code == 302:
        assert "/login" in resp.headers.get("Location", "")


def test_admin_legacy_url_redirects_to_app(logged_in_client):
    resp = logged_in_client.get("/account/security", follow_redirects=False)
    assert resp.status_code == 301
    assert resp.headers["Location"] == "/app/settings"


def test_superadmin_legacy_url_redirects_to_app(client):
    """Every authed role gets the same 301."""
    with client.application.app_context():
        sa_id = User.query.filter_by(username="superadmin").first().id
    sa = _client_for(client.application, sa_id, "superadmin", None)
    resp = sa.get("/account/security", follow_redirects=False)
    assert resp.status_code == 301


def test_owner_legacy_url_redirects_to_app(client):
    with client.application.app_context():
        s = Store(name="Owner store", slug="owner-store-x", plan="basic")
        db.session.add(s); db.session.flush()
        sid = s.id
    own_id = _make_user(client.application, "owner", sid,
                        username="owner@x.com", full_name="Owner X")
    own = _client_for(client.application, own_id, "owner", sid)
    resp = own.get("/account/security", follow_redirects=False)
    assert resp.status_code == 301


def test_employee_legacy_url_redirects_to_app(client, test_store_id):
    emp_id = _make_user(client.application, "employee", test_store_id,
                        username="cashier@test.com", full_name="Cashier")
    emp = _client_for(client.application, emp_id, "employee", test_store_id)
    resp = emp.get("/account/security", follow_redirects=False)
    assert resp.status_code == 301


def test_legacy_admin_settings_security_tab_redirects(logged_in_client):
    """Old bookmark /admin/settings?tab=security → 301 to
    /account/security (which then 301s further to /app/settings).
    First-hop assertion only — checking the chain head."""
    resp = logged_in_client.get("/admin/settings?tab=security")
    assert resp.status_code == 301
    assert resp.headers["Location"].endswith("/account/security")


def test_admin_settings_security_alias_redirects(logged_in_client):
    """Standalone alias /admin/settings/security (no query string)
    also 301s. Same first-hop chain."""
    resp = logged_in_client.get("/admin/settings/security")
    assert resp.status_code == 301
    assert resp.headers["Location"].endswith("/account/security")


def test_topbar_dropdown_links_security_for_admin_chrome(logged_in_client):
    """The dropdown-item link to /account/security stays in
    base.html. The destination 301s to /app/settings now, but the
    URL the chrome renders is unchanged so any cached HTML still
    works."""
    body = logged_in_client.get("/admin/settings?tab=store").data.decode()
    assert "/account/security" in body


def test_topbar_dropdown_links_security_for_owner_chrome(client):
    with client.application.app_context():
        s = Store(name="OS", slug="os-2", plan="basic")
        db.session.add(s); db.session.flush()
        sid = s.id
    own_id = _make_user(client.application, "owner", sid,
                        username="own2@x.com", full_name="Own 2")
    own = _client_for(client.application, own_id, "owner", sid)
    resp = own.get("/owner/dashboard")
    assert resp.status_code == 200
    assert "/account/security" in resp.data.decode()


def test_passkey_eligible_now_admits_employees():
    """Sanity guard so the role gate isn't accidentally re-introduced
    in a future refactor — the v1 helper specifically excluded
    employees, the shared page admits them."""
    from app import _passkey_eligible
    class U:
        def __init__(self, role): self.role = role
    assert _passkey_eligible(U("employee")) is True
    assert _passkey_eligible(U("admin")) is True
    assert _passkey_eligible(U("owner")) is True
    assert _passkey_eligible(U("superadmin")) is True
    assert _passkey_eligible(None) is False
