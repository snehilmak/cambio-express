"""Shared `/account/security` page — every logged-in role can reach it.

The page hosts password change, display-name edit, and passkey
enrollment. This file covers:

  - Cross-role access: admin, owner, employee, superadmin all GET 200.
  - Anonymous users get bounced to login.
  - The legacy /admin/settings?tab=security URL 301s here so old
    bookmarks keep working.
  - The standalone alias /admin/settings/security 301s too.
  - Display-name edits validate empty + over-length input and
    persist on success.
  - Topbar dropdowns in both base.html and base_owner.html link here.
  - The page no longer hides the Passkeys card by role — the
    employee role (which v1 explicitly excluded) now sees it too.

Password validation is exercised in test_account_management.py;
passkey enrollment paths are exercised in test_passkeys.py. We do NOT
re-cover those here.
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
    assert resp.status_code in (302, 401)
    if resp.status_code == 302:
        assert "/login" in resp.headers.get("Location", "")


def test_admin_can_open_security_page(logged_in_client):
    resp = logged_in_client.get("/account/security")
    assert resp.status_code == 200
    body = resp.data.decode()
    # Two cards always present (display name moved to /account/profile)
    assert "Change password" in body
    assert "Passkeys" in body
    # JS bundle pulled in for passkey enrollment
    assert "passkeys.js" in body


def test_superadmin_can_open_security_page(client):
    """The whole reason this page exists — superadmin previously had no
    settings surface and so couldn't enroll a passkey from anywhere."""
    with client.application.app_context():
        sa_id = User.query.filter_by(username="superadmin").first().id
    sa = _client_for(client.application, sa_id, "superadmin", None)
    resp = sa.get("/account/security")
    assert resp.status_code == 200
    body = resp.data.decode()
    assert "Change password" in body
    assert "Passkeys" in body


def test_owner_can_open_security_page(client):
    with client.application.app_context():
        s = Store(name="Owner store", slug="owner-store-x", plan="basic")
        db.session.add(s); db.session.flush()
        sid = s.id
    own_id = _make_user(client.application, "owner", sid,
                        username="owner@x.com", full_name="Owner X")
    own = _client_for(client.application, own_id, "owner", sid)
    resp = own.get("/account/security")
    assert resp.status_code == 200
    assert "Passkeys" in resp.data.decode()


def test_employee_can_open_security_page(client, test_store_id):
    """v1 explicitly hid the passkey card from employees. The shared
    page drops that gate — every logged-in user gets the same surface."""
    emp_id = _make_user(client.application, "employee", test_store_id,
                        username="cashier@test.com", full_name="Cashier")
    emp = _client_for(client.application, emp_id, "employee", test_store_id)
    resp = emp.get("/account/security")
    assert resp.status_code == 200
    body = resp.data.decode()
    assert "Passkeys" in body, \
        "employees should now see the Passkeys card on /account/security"


def test_legacy_admin_settings_security_tab_redirects(logged_in_client):
    """Old bookmark /admin/settings?tab=security → 301 to new page.
    The redirect must be a real 301 (not a 302) so browsers update
    bookmarks; the code path lives in the admin_settings GET branch."""
    resp = logged_in_client.get("/admin/settings?tab=security")
    assert resp.status_code == 301
    assert resp.headers["Location"].endswith("/account/security")


def test_admin_settings_security_alias_redirects(logged_in_client):
    """Standalone alias /admin/settings/security (no query string)
    also 301s — saves anyone who shortened the bookmark."""
    resp = logged_in_client.get("/admin/settings/security")
    assert resp.status_code == 301
    assert resp.headers["Location"].endswith("/account/security")


def test_admin_settings_no_longer_renders_inline_security_form(logged_in_client):
    """The Change Password form used to live inside admin_settings.
    Make sure it's gone (no double-source-of-truth) and that the
    sidebar nav still points users at the new page."""
    body = logged_in_client.get("/admin/settings?tab=store").data.decode()
    assert "Change Password" not in body
    assert 'href="/account/security"' in body or "/account/security" in body


def test_display_name_action_rejected_here(logged_in_client):
    """Display name moved to /account/profile. Posting it to the
    Security endpoint with an _action it no longer handles must 400 —
    not silently fall through and accidentally update something else."""
    resp = logged_in_client.post("/account/security", data={
        "_action": "display_name",
        "full_name": "Brand New Name",
    })
    assert resp.status_code == 400


def test_unknown_action_400(logged_in_client):
    resp = logged_in_client.post("/account/security", data={"_action": "bogus"})
    assert resp.status_code == 400


def test_topbar_dropdown_links_security_for_admin_chrome(logged_in_client):
    """Every page that extends base.html (admin / employee / superadmin
    chrome) gets the Security link in the avatar dropdown. We probe
    via /admin/settings — any base.html page would do."""
    body = logged_in_client.get("/admin/settings?tab=store").data.decode()
    # The dropdown-item link to /account/security is unique enough to
    # assert against literally.
    assert "/account/security" in body


def test_topbar_dropdown_links_security_for_owner_chrome(client):
    """base_owner.html also got the Security link. Render
    /owner_dashboard with an owner session and check the link is
    rendered in the dropdown."""
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
