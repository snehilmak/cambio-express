"""HTTP integration tests for the SPA passkey list + delete endpoints.

  GET    /api/v2/auth/passkeys
  DELETE /api/v2/auth/passkeys/{id}

Enrollment and WebAuthn login verification still live on legacy
Flask routes — those need browser-side `navigator.credentials`
orchestration that's a separate migration. List + delete are pure
server-side and ship here so /app/settings can show the user's
registered devices without bouncing.
"""
from datetime import datetime


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


def _seed_passkey(user_id, *, name="Test Passkey", credential_id=None):
    from app import Passkey, db
    p = Passkey(
        user_id=user_id,
        credential_id=credential_id or f"cred_{user_id}_{name}".encode(),
        public_key=b"fake_pub_key",
        sign_count=0,
        name=name,
        aaguid="00000000-0000-0000-0000-000000000000",
        transports="internal",
    )
    db.session.add(p); db.session.commit()
    return p.id


# ── Auth gating ─────────────────────────────────────────────


def test_list_requires_jwt(client):
    resp = client.get("/api/v2/auth/passkeys")
    assert resp.status_code == 401


def test_delete_requires_jwt(client):
    resp = client.delete("/api/v2/auth/passkeys/1")
    assert resp.status_code == 401


# ── List ────────────────────────────────────────────────────


def test_list_empty_returns_zero(client, test_store_id):
    token = _login_admin(client, test_store_id)
    resp = client.get(
        "/api/v2/auth/passkeys",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.get_json() == {"passkeys": [], "total": 0}


def test_list_returns_users_passkeys(client, test_store_id, test_admin_id):
    from app import app as flask_app
    with flask_app.app_context():
        _seed_passkey(test_admin_id, name="MacBook")
        _seed_passkey(test_admin_id, name="iPhone",
                      credential_id=b"cred_phone")
    token = _login_admin(client, test_store_id)
    body = client.get(
        "/api/v2/auth/passkeys",
        headers={"Authorization": f"Bearer {token}"},
    ).get_json()
    assert body["total"] == 2
    names = {p["name"] for p in body["passkeys"]}
    assert names == {"MacBook", "iPhone"}


def test_list_does_not_leak_credential_id_or_public_key(client, test_store_id, test_admin_id):
    """The raw credential bytes never leave the server — the SPA
    only needs the metadata to render the device list."""
    from app import app as flask_app
    with flask_app.app_context():
        _seed_passkey(test_admin_id, name="Sensitive")
    token = _login_admin(client, test_store_id)
    body = client.get(
        "/api/v2/auth/passkeys",
        headers={"Authorization": f"Bearer {token}"},
    ).get_json()
    row = body["passkeys"][0]
    assert "credential_id" not in row
    assert "public_key" not in row
    assert "sign_count" not in row


def test_list_excludes_other_users_passkeys(client, test_store_id, test_admin_id):
    """Cross-user isolation: another user's passkey must not surface."""
    from app import User, db, app as flask_app
    with flask_app.app_context():
        # Seed another user with a passkey
        other = User(
            store_id=test_store_id, username="other@test.com",
            full_name="Other", role="employee",
        )
        other.set_password("x")
        db.session.add(other); db.session.commit()
        _seed_passkey(other.id, name="OtherDevice",
                      credential_id=b"cred_other")
        # And one for the seeded admin
        _seed_passkey(test_admin_id, name="MyDevice")
    token = _login_admin(client, test_store_id)
    body = client.get(
        "/api/v2/auth/passkeys",
        headers={"Authorization": f"Bearer {token}"},
    ).get_json()
    names = {p["name"] for p in body["passkeys"]}
    assert names == {"MyDevice"}


# ── Delete ──────────────────────────────────────────────────


def test_delete_removes_passkey(client, test_store_id, test_admin_id):
    from app import app as flask_app, Passkey
    with flask_app.app_context():
        pid = _seed_passkey(test_admin_id, name="ToDelete")
    token = _login_admin(client, test_store_id)
    resp = client.delete(
        f"/api/v2/auth/passkeys/{pid}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 204
    with flask_app.app_context():
        assert Passkey.query.filter_by(id=pid).first() is None


def test_delete_404_when_missing(client, test_store_id):
    token = _login_admin(client, test_store_id)
    resp = client.delete(
        "/api/v2/auth/passkeys/9999999",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404


def test_delete_404_for_another_users_passkey(client, test_store_id, test_admin_id):
    """Deleting someone else's passkey returns 404, never 200 or
    403 — that would leak the existence of the row."""
    from app import User, db, app as flask_app
    with flask_app.app_context():
        other = User(
            store_id=test_store_id, username="alien@test.com",
            full_name="Alien", role="employee",
        )
        other.set_password("x")
        db.session.add(other); db.session.commit()
        other_pid = _seed_passkey(other.id, name="AlienDevice",
                                  credential_id=b"cred_alien")
    _ = test_admin_id
    token = _login_admin(client, test_store_id)
    resp = client.delete(
        f"/api/v2/auth/passkeys/{other_pid}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404
