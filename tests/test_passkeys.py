"""Passkey (WebAuthn) integration tests.

We don't simulate the crypto ceremony end-to-end — that would require a
browser-side authenticator emulator. Instead we assert:

  - Schema + model CRUD (a Passkey row links to a user and survives
    orm queries).
  - Registration BEGIN returns the expected options shape and stores
    a challenge in the session so FINISH has something to verify
    against.
  - FINISH gracefully rejects a malformed body / missing challenge /
    bad credential.
  - DELETE removes only the caller's passkey.
  - Authentication BEGIN is anonymous; it stores a challenge.
  - Authentication FINISH rejects a missing / unknown credential
    without leaking account enumeration signals beyond a 400.
  - The UI surfaces render the expected markup on the Security tab
    and on the login page.
  - _passkey_eligible() gates admin/owner/superadmin in; employee out.
  - The store-purge path cleans up Passkey rows so a user delete
    doesn't hit a dangling FK on Postgres.
"""
import json
from datetime import date, datetime, timedelta


def _superadmin_client(client):
    from app import User
    with client.application.app_context():
        uid = User.query.filter_by(username="superadmin", store_id=None).first().id
    with client.session_transaction() as s:
        s["user_id"] = uid
        s["role"] = "superadmin"
    return client


def _make_passkey(app, user_id, credential_id=b"cred123", name="Test key"):
    from app import Passkey, db
    with app.app_context():
        pk = Passkey(
            user_id=user_id,
            credential_id=credential_id,
            public_key=b"fake-public-key",
            sign_count=0,
            name=name,
        )
        db.session.add(pk)
        db.session.commit()
        return pk.id


def test_model_roundtrip(logged_in_client, test_admin_id):
    from app import Passkey, db
    pk_id = _make_passkey(logged_in_client.application, test_admin_id,
                          credential_id=b"abc-credential", name="MacBook")
    with logged_in_client.application.app_context():
        row = db.session.get(Passkey, pk_id)
        assert row is not None
        assert row.user_id == test_admin_id
        assert row.credential_id == b"abc-credential"
        assert row.public_key == b"fake-public-key"
        assert row.name == "MacBook"
        assert row.sign_count == 0
        assert row.last_used_at is None


def test_register_begin_options_shape(logged_in_client, test_admin_id):
    """Admin can start registration. Response is WebAuthn options JSON;
    server stashes the challenge in session for the finish step."""
    resp = logged_in_client.post("/account/passkeys/register/begin")
    assert resp.status_code == 200
    opts = json.loads(resp.data)
    assert opts["rp"]["name"] == "DineroBook"
    assert "challenge" in opts and opts["challenge"]
    assert opts["user"]["name"] == "admin@test.com"
    # Discoverable creds — residentKey required + resident verification
    assert opts["authenticatorSelection"]["residentKey"] == "required"
    assert "excludeCredentials" in opts
    with logged_in_client.session_transaction() as s:
        assert "pk_reg_challenge" in s
        assert len(s["pk_reg_challenge"]) > 0


def test_register_begin_excludes_existing_passkeys(logged_in_client, test_admin_id):
    """An already-registered credential appears in the excludeCredentials
    list so the same authenticator can't be re-registered to the same
    account — the browser will refuse."""
    _make_passkey(logged_in_client.application, test_admin_id,
                  credential_id=b"already-there")
    resp = logged_in_client.post("/account/passkeys/register/begin")
    opts = json.loads(resp.data)
    # The excludeCredentials id is base64url of the stored raw bytes.
    import base64
    expected = base64.urlsafe_b64encode(b"already-there").rstrip(b"=").decode()
    ids = [c["id"] for c in opts["excludeCredentials"]]
    assert expected in ids, (
        f"existing credential id not excluded; got {ids!r}, expected {expected!r}")


def test_register_finish_without_session_challenge_rejects(logged_in_client):
    resp = logged_in_client.post(
        "/account/passkeys/register/finish",
        data=json.dumps({"credential": {"id": "xxx"}}),
        content_type="application/json",
    )
    assert resp.status_code == 400
    payload = json.loads(resp.data)
    assert payload["ok"] is False
    assert "in progress" in payload["error"].lower()


def test_register_finish_with_missing_credential_rejects(logged_in_client):
    # Prime a challenge first so we pass that gate
    logged_in_client.post("/account/passkeys/register/begin")
    resp = logged_in_client.post(
        "/account/passkeys/register/finish",
        data=json.dumps({"name": "Phone"}),  # no credential key
        content_type="application/json",
    )
    assert resp.status_code == 400
    assert "credential" in json.loads(resp.data)["error"].lower()


def test_register_finish_with_bad_credential_rejects(logged_in_client):
    logged_in_client.post("/account/passkeys/register/begin")
    resp = logged_in_client.post(
        "/account/passkeys/register/finish",
        data=json.dumps({"credential": {"id": "bogus", "rawId": "bogus",
                                        "type": "public-key",
                                        "response": {"clientDataJSON": "x",
                                                     "attestationObject": "y"}}}),
        content_type="application/json",
    )
    # Library raises on invalid attestation — we normalize to 400 with a
    # message that mentions verification.
    assert resp.status_code == 400
    assert "verified" in json.loads(resp.data)["error"].lower()


def test_register_begin_requires_login(client):
    resp = client.post("/account/passkeys/register/begin")
    # login_required redirects to /login rather than 401
    assert resp.status_code in (302, 401)


def test_register_now_open_to_employee_role(logged_in_client, test_store_id):
    """v1 explicitly excluded employees from passkey enrollment. The
    shared /account/security page drops that gate — every logged-in
    user can enroll, including employees. This test was previously
    asserting the opposite; flipped here to lock in the new behavior
    so a future refactor doesn't quietly re-introduce the role gate."""
    from tests.conftest import make_employee_client
    emp = make_employee_client(test_store_id)
    resp = emp.post("/account/passkeys/register/begin")
    assert resp.status_code == 200
    import json
    payload = json.loads(resp.data)
    assert "challenge" in payload


def test_delete_only_removes_own_passkey(logged_in_client, test_admin_id):
    from app import Passkey, User, db
    pk_id = _make_passkey(logged_in_client.application, test_admin_id,
                          credential_id=b"mine")
    # Second user with their own passkey
    other_user_id = _create_other_admin(logged_in_client.application)
    other_pk_id = _make_passkey(logged_in_client.application, other_user_id,
                                credential_id=b"not-mine")
    # Logged-in user cannot delete the other user's passkey.
    resp = logged_in_client.post(f"/account/passkeys/{other_pk_id}/delete")
    assert resp.status_code == 404
    # Can delete own passkey.
    resp = logged_in_client.post(f"/account/passkeys/{pk_id}/delete")
    assert resp.status_code in (200, 302)
    with logged_in_client.application.app_context():
        assert db.session.get(Passkey,pk_id) is None
        assert db.session.get(Passkey,other_pk_id) is not None


def _create_other_admin(app):
    from app import User, Store, db
    with app.app_context():
        s = Store(name="Other", slug="other-x", plan="trial")
        db.session.add(s); db.session.flush()
        u = User(store_id=s.id, username="other-admin@x.com",
                 full_name="Other Admin", role="admin")
        u.set_password("x")
        db.session.add(u); db.session.commit()
        return u.id


def test_login_begin_anonymous(client):
    resp = client.post("/login/passkey/begin")
    assert resp.status_code == 200
    opts = json.loads(resp.data)
    assert "challenge" in opts and opts["challenge"]
    # allowCredentials is empty in discoverable-creds mode
    assert opts.get("allowCredentials", []) == []
    with client.session_transaction() as s:
        assert "pk_login_challenge" in s


def test_login_finish_without_challenge_rejects(client):
    resp = client.post(
        "/login/passkey/finish",
        data=json.dumps({"credential": {"id": "x", "rawId": "x", "type": "public-key"}}),
        content_type="application/json",
    )
    assert resp.status_code == 400
    assert "challenge" in json.loads(resp.data)["error"].lower()


def test_login_finish_unknown_credential_rejects(client):
    client.post("/login/passkey/begin")  # prime challenge
    resp = client.post(
        "/login/passkey/finish",
        data=json.dumps({"credential": {
            "id": "aaaa", "rawId": "aaaa", "type": "public-key",
            "response": {"clientDataJSON": "x", "authenticatorData": "y",
                          "signature": "z"},
        }}),
        content_type="application/json",
    )
    assert resp.status_code == 400
    msg = json.loads(resp.data)["error"].lower()
    assert "recognized" in msg or "invalid" in msg


def test_passkey_eligible_helper():
    """v1 admitted only admin/owner/superadmin. The helper now admits
    every logged-in user; the role-deeper check moved to the rendering
    template (which always shows the card for any non-None user)."""
    from app import _passkey_eligible
    class U:
        def __init__(self, role): self.role = role
    assert _passkey_eligible(U("admin")) is True
    assert _passkey_eligible(U("owner")) is True
    assert _passkey_eligible(U("superadmin")) is True
    assert _passkey_eligible(U("employee")) is True
    assert _passkey_eligible(None) is False


def test_account_security_page_shows_passkey_card(logged_in_client):
    """The Passkeys card moved off /admin/settings's Security tab and
    onto the shared /account/security page. Same markup contract."""
    resp = logged_in_client.get("/account/security")
    assert resp.status_code == 200
    body = resp.data.decode()
    assert 'id="passkeys-card"' in body
    assert "Add a passkey" in body
    assert "passkeys.js" in body
    assert "No passkeys registered yet" in body


def test_account_security_page_lists_registered_passkeys(logged_in_client, test_admin_id):
    _make_passkey(logged_in_client.application, test_admin_id,
                  credential_id=b"one-key", name="iPhone")
    body = logged_in_client.get("/account/security").data.decode()
    assert "iPhone" in body
    import re
    m = re.search(r'<tfoot id="pk-empty"([^>]*)>', body)
    assert m, "tfoot pk-empty missing"
    assert "hidden" in m.group(1), \
        f"tfoot should be hidden when passkeys exist; got: {m.group(1)!r}"


def test_login_page_ships_passkey_button(client):
    body = client.get("/login").data.decode()
    # Button itself + the JS helper + the divider
    assert 'id="pk-login-btn"' in body
    assert "Sign in with a passkey" in body
    assert "passkeys.js" in body
    # Button is hidden by default; JS un-hides it when WebAuthn is present
    assert 'id="pk-login-btn" class="btn-passkey" hidden' in body


def test_purge_cascades_passkey_rows(client):
    """When a store is purged under retention, its users' Passkey rows
    must go too — otherwise the User delete would FK-fail on Postgres."""
    from app import Store, User, Passkey, db, purge_expired_stores
    _superadmin_client(client)
    with client.application.app_context():
        s = Store(name="Doomed", slug="doomed-xyz", plan="inactive",
                  is_active=False,
                  data_retention_until=datetime.utcnow() - timedelta(days=1))
        db.session.add(s); db.session.flush()
        u = User(store_id=s.id, username="admin@doomed",
                 full_name="Doomed Admin", role="admin")
        u.set_password("x")
        db.session.add(u); db.session.flush()
        pk = Passkey(user_id=u.id, credential_id=b"doomed-cred",
                     public_key=b"pk", sign_count=0)
        db.session.add(pk); db.session.commit()
        pk_id = pk.id

        n = purge_expired_stores()
        assert n == 1, f"expected 1 purge, got {n}"
        assert db.session.get(Passkey,pk_id) is None, \
            "Passkey rows must be removed alongside their user"
