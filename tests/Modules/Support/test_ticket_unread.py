"""In-app unread badge for support tickets.

  GET /tickets/unread     — per-side total (store side vs staff)
  GET /tickets            — per-ticket ``unread_count``
  GET /tickets/{id}/messages — stamps the caller's side's read
                               receipt (clears the badge)

The read state is per conversation SIDE (shared inbox), not per
person — mirrors the store-scoped list endpoints.
"""
import pytest
from tests._app import db, db_session
from tests.conftest import login_admin, login_superadmin


@pytest.fixture
def sa_headers(client):
    return {"Authorization": f"Bearer {login_superadmin(client)}"}


@pytest.fixture
def admin_headers(client):
    with db_session():
        from api.Modules.Tenancy.Models import Store
        store_id = db.session.query(Store).first().id
    return {"Authorization": f"Bearer {login_admin(client, store_id)}"}


def _make_ticket(client, headers, subject="Unread test"):
    resp = client.post("/api/v2/tickets", headers=headers, json={
        "category": "question", "subject": subject, "body": "Help please.",
    })
    assert resp.status_code == 201
    return resp.json()["ticket"]["id"]


def _unread(client, headers):
    resp = client.get("/api/v2/tickets/unread", headers=headers)
    assert resp.status_code == 200
    return resp.json()["unread"]


class TestUnreadBadge:
    def test_staff_reply_lights_user_badge(
        self, client, admin_headers, sa_headers,
    ):
        tid = _make_ticket(client, admin_headers)
        assert _unread(client, admin_headers) == 0
        client.post(
            f"/api/v2/tickets/{tid}/messages", headers=sa_headers,
            json={"body": "We are on it."},
        )
        assert _unread(client, admin_headers) == 1
        # And the list row carries the per-ticket count.
        rows = client.get(
            "/api/v2/tickets", headers=admin_headers,
        ).json()["tickets"]
        assert rows[0]["unread_count"] == 1

    def test_opening_thread_clears_user_badge(
        self, client, admin_headers, sa_headers,
    ):
        tid = _make_ticket(client, admin_headers)
        client.post(
            f"/api/v2/tickets/{tid}/messages", headers=sa_headers,
            json={"body": "Reply one."},
        )
        # Opening the thread stamps the store side's read receipt.
        client.get(f"/api/v2/tickets/{tid}/messages", headers=admin_headers)
        assert _unread(client, admin_headers) == 0
        rows = client.get(
            "/api/v2/tickets", headers=admin_headers,
        ).json()["tickets"]
        assert rows[0]["unread_count"] == 0

    def test_user_reply_lights_staff_badge(
        self, client, admin_headers, sa_headers,
    ):
        tid = _make_ticket(client, admin_headers)
        # Creating a ticket appends no thread message, so staff
        # starts at 0 — the badge counts replies, not new tickets
        # (those already land as email notifications).
        base = _unread(client, sa_headers)
        client.post(
            f"/api/v2/tickets/{tid}/messages", headers=admin_headers,
            json={"body": "Adding more detail."},
        )
        assert _unread(client, sa_headers) == base + 1
        client.get(f"/api/v2/tickets/{tid}/messages", headers=sa_headers)
        assert _unread(client, sa_headers) == base

    def test_own_replies_never_count_as_unread(
        self, client, admin_headers,
    ):
        tid = _make_ticket(client, admin_headers)
        client.post(
            f"/api/v2/tickets/{tid}/messages", headers=admin_headers,
            json={"body": "Talking to myself."},
        )
        assert _unread(client, admin_headers) == 0

    def test_sides_are_independent(
        self, client, admin_headers, sa_headers,
    ):
        tid = _make_ticket(client, admin_headers)
        client.post(
            f"/api/v2/tickets/{tid}/messages", headers=sa_headers,
            json={"body": "Staff reply."},
        )
        # Staff opening THEIR side must not clear the store side.
        client.get(f"/api/v2/tickets/{tid}/messages", headers=sa_headers)
        assert _unread(client, admin_headers) == 1

    def test_multiple_replies_accumulate(
        self, client, admin_headers, sa_headers,
    ):
        tid = _make_ticket(client, admin_headers)
        for i in range(3):
            client.post(
                f"/api/v2/tickets/{tid}/messages", headers=sa_headers,
                json={"body": f"Reply {i}."},
            )
        assert _unread(client, admin_headers) == 3

    def test_unread_requires_auth(self, client):
        resp = client.get("/api/v2/tickets/unread")
        assert resp.status_code in (401, 403)
