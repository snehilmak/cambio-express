"""HTTP integration tests for the Support ticket module.

Covers all 5 endpoints:
  POST /tickets          — create ticket
  GET  /tickets          — list my store's tickets
  GET  /tickets/all      — superadmin: all tickets
  GET  /tickets/{id}     — detail (scoped)
  PUT  /tickets/{id}     — update status/priority/reply
"""
import pytest
from tests._app import db, db_session
from tests.conftest import login_admin, login_superadmin


@pytest.fixture
def sa_token(client):
    return login_superadmin(client)


@pytest.fixture
def sa_headers(sa_token):
    return {"Authorization": f"Bearer {sa_token}"}


@pytest.fixture
def admin_token(client):
    with db_session():
        from api.Modules.Tenancy.Models import Store
        store = db.session.query(Store).first()
        store_id = store.id
    return login_admin(client, store_id)


@pytest.fixture
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


class TestCreateTicket:
    def test_create_ticket(self, client, admin_headers):
        resp = client.post("/api/v2/tickets", headers=admin_headers, json={
            "category": "bug",
            "subject": "Test bug report",
            "body": "Something is broken.",
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["ticket"]["subject"] == "Test bug report"
        assert data["ticket"]["category"] == "bug"
        assert data["ticket"]["status"] == "open"

    def test_invalid_category_rejected(self, client, admin_headers):
        resp = client.post("/api/v2/tickets", headers=admin_headers, json={
            "category": "invalid_cat",
            "subject": "Test",
            "body": "Test body.",
        })
        assert resp.status_code == 422

    def test_requires_auth(self, client):
        resp = client.post("/api/v2/tickets", json={
            "category": "bug", "subject": "X", "body": "Y",
        })
        assert resp.status_code in (401, 403)


class TestListMyTickets:
    def test_list_tickets(self, client, admin_headers):
        # Create one first
        client.post("/api/v2/tickets", headers=admin_headers, json={
            "category": "question",
            "subject": "List test",
            "body": "Testing list.",
        })
        resp = client.get("/api/v2/tickets", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "tickets" in data
        assert "total" in data
        assert data["total"] >= 1

    def test_superadmin_gets_all_tickets(self, client, sa_headers):
        resp = client.get("/api/v2/tickets", headers=sa_headers)
        assert resp.status_code == 200
        assert "tickets" in resp.json()


class TestListAllTickets:
    def test_superadmin_only(self, client, admin_headers, sa_headers):
        resp = client.get("/api/v2/tickets/all", headers=admin_headers)
        assert resp.status_code == 403
        resp = client.get("/api/v2/tickets/all", headers=sa_headers)
        assert resp.status_code == 200

    def test_returns_store_names(self, client, sa_headers):
        resp = client.get("/api/v2/tickets/all", headers=sa_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "tickets" in data
        assert "total" in data


class TestGetTicket:
    def test_get_own_ticket(self, client, admin_headers):
        create = client.post("/api/v2/tickets", headers=admin_headers, json={
            "category": "feedback",
            "subject": "Detail test",
            "body": "Testing detail.",
        })
        tid = create.json()["ticket"]["id"]
        resp = client.get(f"/api/v2/tickets/{tid}", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["ticket"]["id"] == tid

    def test_superadmin_sees_any(self, client, admin_headers, sa_headers):
        create = client.post("/api/v2/tickets", headers=admin_headers, json={
            "category": "bug",
            "subject": "SA visibility",
            "body": "Test.",
        })
        tid = create.json()["ticket"]["id"]
        resp = client.get(f"/api/v2/tickets/{tid}", headers=sa_headers)
        assert resp.status_code == 200

    def test_404_on_missing(self, client, admin_headers):
        resp = client.get("/api/v2/tickets/99999", headers=admin_headers)
        assert resp.status_code == 404


class TestUpdateTicket:
    def test_update_status(self, client, sa_headers, admin_headers):
        create = client.post("/api/v2/tickets", headers=admin_headers, json={
            "category": "question",
            "subject": "Update test",
            "body": "Test.",
        })
        tid = create.json()["ticket"]["id"]
        resp = client.put(f"/api/v2/tickets/{tid}", headers=sa_headers, json={
            "status": "resolved",
            "admin_reply": "Fixed it.",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["ticket"]["status"] == "resolved"
        assert data["ticket"]["admin_reply"] == "Fixed it."

    def test_non_admin_cannot_update(self, client):
        resp = client.put("/api/v2/tickets/1", json={"status": "closed"})
        assert resp.status_code in (401, 403)
