"""Backend parity for the shared field-validation library.

The SPA validates email shape client-side (frontend/src/lib/validators.ts);
the server re-validates the same rule on the superadmin store create /
update endpoints because the server is the real trust boundary. A
malformed email must 422 regardless of what the client sent.
"""
import pytest

from tests.conftest import login_superadmin


@pytest.fixture
def sa_headers(client):
    return {"Authorization": f"Bearer {login_superadmin(client)}"}


def _create_payload(**over):
    base = {
        "name": "Validated Branch",
        "slug": "validated-branch",
        "email": "ok@example.com",
        "phone": "",
        "address": "1 Main St",
        "plan": "trial",
        "admin_username": "vbadmin",
        "admin_name": "VB Admin",
        "admin_password": "vbpass123!",
    }
    base.update(over)
    return base


class TestCreateEmailValidation:
    def test_invalid_email_rejected(self, client, sa_headers):
        resp = client.post(
            "/api/v2/superadmin/stores",
            headers=sa_headers,
            json=_create_payload(email="not-an-email", slug="bad-email-create"),
        )
        assert resp.status_code == 422

    def test_valid_email_accepted(self, client, sa_headers):
        resp = client.post(
            "/api/v2/superadmin/stores",
            headers=sa_headers,
            json=_create_payload(email="good@example.com", slug="good-email-create"),
        )
        assert resp.status_code == 201

    def test_empty_email_allowed(self, client, sa_headers):
        # Email is optional on a store — empty must pass.
        resp = client.post(
            "/api/v2/superadmin/stores",
            headers=sa_headers,
            json=_create_payload(email="", slug="no-email-create"),
        )
        assert resp.status_code == 201


class TestUpdateEmailValidation:
    def test_invalid_email_rejected(self, client, sa_headers, test_store_id):
        resp = client.patch(
            f"/api/v2/superadmin/stores/{test_store_id}",
            headers=sa_headers,
            json={"email": "still-not-an-email"},
        )
        assert resp.status_code == 422

    def test_valid_email_accepted(self, client, sa_headers, test_store_id):
        resp = client.patch(
            f"/api/v2/superadmin/stores/{test_store_id}",
            headers=sa_headers,
            json={"email": "updated@example.com"},
        )
        assert resp.status_code == 200
