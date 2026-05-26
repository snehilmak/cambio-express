"""Tests for Tier 2 superadmin features: billing overview, email log,
store deep-drill, change-role action."""
import pytest
from tests._app import db, db_session
from tests.conftest import login_superadmin


@pytest.fixture
def sa_token(client):
    return login_superadmin(client)


@pytest.fixture
def sa_headers(sa_token):
    return {"Authorization": f"Bearer {sa_token}"}


class TestBillingOverview:
    def test_returns_billing_data(self, client, sa_headers):
        resp = client.get("/api/v2/superadmin/billing-overview", headers=sa_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "expiring_soon" in data
        assert "in_grace" in data
        assert "retention_queue" in data
        assert "recent_cancels" in data
        assert "webhook_stats" in data
        assert isinstance(data["expiring_soon"], list)

    def test_requires_superadmin(self, client):
        resp = client.get("/api/v2/superadmin/billing-overview")
        assert resp.status_code in (401, 403)


class TestEmailLog:
    def test_returns_email_log(self, client, sa_headers):
        resp = client.get("/api/v2/superadmin/email-log", headers=sa_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "rows" in data
        assert "total" in data
        assert "page" in data
        assert "total_pages" in data
        assert "suppressed" in data

    def test_requires_superadmin(self, client):
        resp = client.get("/api/v2/superadmin/email-log")
        assert resp.status_code in (401, 403)

    def test_pagination(self, client, sa_headers):
        resp = client.get(
            "/api/v2/superadmin/email-log?page=1&per_page=10",
            headers=sa_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["page"] == 1


class TestStoreDrill:
    def test_returns_store_data(self, client, sa_headers):
        with db_session():
            from api.Modules.Tenancy.Models import Store
            store = db.session.query(Store).first()
            assert store is not None
            store_id = store.id
        resp = client.get(
            f"/api/v2/superadmin/stores/{store_id}/drill",
            headers=sa_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["store"]["id"] == store_id
        assert "team" in data
        assert "roster" in data
        assert "recent_transfers" in data
        assert "stats_30d" in data
        assert "transfer_count" in data["stats_30d"]
        assert "volume" in data["stats_30d"]

    def test_404_for_missing_store(self, client, sa_headers):
        resp = client.get(
            "/api/v2/superadmin/stores/99999/drill",
            headers=sa_headers,
        )
        assert resp.status_code == 404

    def test_requires_superadmin(self, client):
        resp = client.get("/api/v2/superadmin/stores/1/drill")
        assert resp.status_code in (401, 403)


class TestChangeRole:
    def test_change_role(self, client, sa_headers):
        with db_session():
            from api.Modules.Tenancy.Models import User
            user = db.session.query(User).filter(
                User.role.in_(["employee", "admin"]),
                User.store_id.isnot(None),
            ).first()
            if user is None:
                pytest.skip("No store user in test DB")
            user_id = user.id
            original_role = user.role

        new_role = "admin" if original_role == "employee" else "employee"
        resp = client.post(
            f"/api/v2/superadmin/users/{user_id}/change-role",
            headers=sa_headers,
            json={"role": new_role},
        )
        assert resp.status_code == 200
        assert resp.json()["role"] == new_role

        # Restore original role
        client.post(
            f"/api/v2/superadmin/users/{user_id}/change-role",
            headers=sa_headers,
            json={"role": original_role},
        )

    def test_cannot_change_superadmin_role(self, client, sa_headers):
        with db_session():
            from api.Modules.Tenancy.Models import User
            sa = db.session.query(User).filter_by(role="superadmin").first()
            sa_id = sa.id
        resp = client.post(
            f"/api/v2/superadmin/users/{sa_id}/change-role",
            headers=sa_headers,
            json={"role": "admin"},
        )
        assert resp.status_code == 403

    def test_invalid_role_rejected(self, client, sa_headers):
        with db_session():
            from api.Modules.Tenancy.Models import User
            user = db.session.query(User).filter(
                User.role != "superadmin", User.store_id.isnot(None),
            ).first()
            if user is None:
                pytest.skip("No non-superadmin user")
            user_id = user.id
        resp = client.post(
            f"/api/v2/superadmin/users/{user_id}/change-role",
            headers=sa_headers,
            json={"role": "hacker"},
        )
        assert resp.status_code == 422

    def test_requires_superadmin(self, client):
        resp = client.post(
            "/api/v2/superadmin/users/1/change-role",
            json={"role": "admin"},
        )
        assert resp.status_code in (401, 403)
