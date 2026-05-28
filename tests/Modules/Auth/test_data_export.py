"""Tests for the user data export endpoint (GDPR portability)."""
import json

from tests.conftest import login_admin, login_superadmin


def _headers(token):
    return {"Authorization": f"Bearer {token}"}


def test_authenticated_user_can_export_their_data(client, test_store_id):
    token = login_admin(client, test_store_id)
    resp = client.get(
        "/api/v2/auth/account/export",
        headers=_headers(token),
    )
    assert resp.status_code == 200
    assert "application/json" in resp.headers.get("content-type", "")
    cd = resp.headers.get("content-disposition", "")
    assert "attachment" in cd
    assert ".json" in cd


def test_export_contains_expected_sections(client, test_store_id):
    token = login_admin(client, test_store_id)
    resp = client.get(
        "/api/v2/auth/account/export",
        headers=_headers(token),
    )
    payload = json.loads(resp.get_data(as_text=True))
    assert "exported_at" in payload
    assert "export_version" in payload
    assert "profile" in payload
    assert "notification_preferences" in payload
    assert "sessions" in payload
    assert "passkeys" in payload
    assert "audit_log_entries" in payload


def test_export_profile_contains_user_fields(client, test_store_id):
    token = login_admin(client, test_store_id)
    resp = client.get(
        "/api/v2/auth/account/export",
        headers=_headers(token),
    )
    payload = json.loads(resp.get_data(as_text=True))
    profile = payload["profile"]
    assert profile["username"] == "admin@test.com"
    assert profile["role"] == "admin"
    assert profile["store_id"] == test_store_id
    assert "user_id" in profile


def test_export_does_not_leak_secrets(client, test_store_id):
    """The export must NOT contain password hashes, TOTP secrets, or
    passkey credential IDs/public keys."""
    token = login_admin(client, test_store_id)
    resp = client.get(
        "/api/v2/auth/account/export",
        headers=_headers(token),
    )
    body = resp.get_data(as_text=True)
    assert "password_hash" not in body
    assert "totp_secret" not in body
    assert "credential_id" not in body
    assert "public_key" not in body


def test_export_requires_auth(client):
    resp = client.get("/api/v2/auth/account/export")
    assert resp.status_code == 401


def test_superadmin_can_export(client):
    token = login_superadmin(client)
    resp = client.get(
        "/api/v2/auth/account/export",
        headers=_headers(token),
    )
    assert resp.status_code == 200
    payload = json.loads(resp.get_data(as_text=True))
    assert payload["profile"]["role"] == "superadmin"


def test_export_filename_includes_username(client, test_store_id):
    token = login_admin(client, test_store_id)
    resp = client.get(
        "/api/v2/auth/account/export",
        headers=_headers(token),
    )
    cd = resp.headers.get("content-disposition", "")
    assert "admin" in cd.lower()
