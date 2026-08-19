"""HTTP integration tests for the ticket conversation thread.

  GET  /tickets/{id}/messages  — thread, oldest first
  POST /tickets/{id}/messages  — reply (409 on closed, auto-reopen
                                 on store-side reply to resolved,
                                 staff dual-write of admin_reply)
  POST /tickets/{id}/reopen    — closed → open
Plus: the legacy PUT admin_reply also appends a staff message.
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


def _make_ticket(client, headers, subject="Thread test"):
    resp = client.post("/api/v2/tickets", headers=headers, json={
        "category": "question", "subject": subject, "body": "Help please.",
    })
    assert resp.status_code == 201
    return resp.json()["ticket"]["id"]


class TestThread:
    def test_user_and_staff_reply_roundtrip(
        self, client, admin_headers, sa_headers,
    ):
        tid = _make_ticket(client, admin_headers)
        r1 = client.post(
            f"/api/v2/tickets/{tid}/messages", headers=admin_headers,
            json={"body": "Adding more detail."},
        )
        assert r1.status_code == 201
        r2 = client.post(
            f"/api/v2/tickets/{tid}/messages", headers=sa_headers,
            json={"body": "We are on it."},
        )
        assert r2.status_code == 201
        thread = client.get(
            f"/api/v2/tickets/{tid}/messages", headers=admin_headers,
        ).json()
        assert thread["total"] == 2
        kinds = [m["author_kind"] for m in thread["messages"]]
        assert kinds == ["user", "staff"]
        assert thread["messages"][0]["body"] == "Adding more detail."

    def test_staff_reply_dual_writes_legacy_column(
        self, client, admin_headers, sa_headers,
    ):
        tid = _make_ticket(client, admin_headers)
        client.post(
            f"/api/v2/tickets/{tid}/messages", headers=sa_headers,
            json={"body": "Latest staff word."},
        )
        detail = client.get(
            f"/api/v2/tickets/{tid}", headers=admin_headers,
        ).json()["ticket"]
        assert detail["admin_reply"] == "Latest staff word."
        assert detail["replied_by"]

    def test_reply_blocked_on_closed(self, client, admin_headers, sa_headers):
        tid = _make_ticket(client, admin_headers)
        client.put(
            f"/api/v2/tickets/{tid}", headers=sa_headers,
            json={"status": "closed"},
        )
        resp = client.post(
            f"/api/v2/tickets/{tid}/messages", headers=admin_headers,
            json={"body": "Hello?"},
        )
        assert resp.status_code == 409

    def test_user_reply_to_resolved_auto_reopens(
        self, client, admin_headers, sa_headers,
    ):
        tid = _make_ticket(client, admin_headers)
        client.put(
            f"/api/v2/tickets/{tid}", headers=sa_headers,
            json={"status": "resolved"},
        )
        resp = client.post(
            f"/api/v2/tickets/{tid}/messages", headers=admin_headers,
            json={"body": "It's still broken."},
        )
        assert resp.status_code == 201
        assert resp.json()["ticket"]["status"] == "open"
        assert resp.json()["ticket"]["closed_at"] is None

    def test_staff_reply_to_resolved_keeps_status(
        self, client, admin_headers, sa_headers,
    ):
        tid = _make_ticket(client, admin_headers)
        client.put(
            f"/api/v2/tickets/{tid}", headers=sa_headers,
            json={"status": "resolved"},
        )
        resp = client.post(
            f"/api/v2/tickets/{tid}/messages", headers=sa_headers,
            json={"body": "Glad it's sorted."},
        )
        assert resp.status_code == 201
        assert resp.json()["ticket"]["status"] == "resolved"


class TestReopen:
    def test_reopen_closed_ticket(self, client, admin_headers, sa_headers):
        tid = _make_ticket(client, admin_headers)
        client.put(
            f"/api/v2/tickets/{tid}", headers=sa_headers,
            json={"status": "closed"},
        )
        resp = client.post(
            f"/api/v2/tickets/{tid}/reopen", headers=admin_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["ticket"]["status"] == "open"
        assert resp.json()["ticket"]["closed_at"] is None

    def test_reopen_rejected_when_not_closed(self, client, admin_headers):
        tid = _make_ticket(client, admin_headers)
        resp = client.post(
            f"/api/v2/tickets/{tid}/reopen", headers=admin_headers,
        )
        assert resp.status_code == 409


class TestScoping:
    def test_cross_store_thread_is_404(self, client, admin_headers, sa_headers):
        """A principal from another store can't see or post into the
        thread — opaque 404, same as the ticket detail."""
        tid = _make_ticket(client, admin_headers)
        with db_session():
            from api.Core.PasswordHash import generate_password_hash
            from api.Modules.Tenancy.Models import Store, User
            other = Store(name="Other Store", slug="other-thread-store")
            db.session.add(other)
            db.session.flush()
            db.session.add(User(
                store_id=other.id, username="other-admin",
                password_hash=generate_password_hash("testpass123!"),
                role="admin", full_name="Other Admin", is_active=True,
            ))
            db.session.commit()
            other_id = other.id
        other_headers = {
            "Authorization": f"Bearer {login_admin(client, other_id)}"
        }
        assert client.get(
            f"/api/v2/tickets/{tid}/messages", headers=other_headers,
        ).status_code == 404
        assert client.post(
            f"/api/v2/tickets/{tid}/messages", headers=other_headers,
            json={"body": "sneaky"},
        ).status_code == 404
        assert client.post(
            f"/api/v2/tickets/{tid}/reopen", headers=other_headers,
        ).status_code == 404


class TestLegacyPutBridge:
    def test_put_admin_reply_appends_staff_message(
        self, client, admin_headers, sa_headers,
    ):
        tid = _make_ticket(client, admin_headers)
        client.put(
            f"/api/v2/tickets/{tid}", headers=sa_headers,
            json={"admin_reply": "Via the legacy field."},
        )
        thread = client.get(
            f"/api/v2/tickets/{tid}/messages", headers=admin_headers,
        ).json()
        assert thread["total"] == 1
        assert thread["messages"][0]["author_kind"] == "staff"
        assert thread["messages"][0]["body"] == "Via the legacy field."


class TestAudit:
    def test_staff_reply_writes_superadmin_audit(
        self, client, admin_headers, sa_headers,
    ):
        tid = _make_ticket(client, admin_headers)
        client.post(
            f"/api/v2/tickets/{tid}/messages", headers=sa_headers,
            json={"body": "audited"},
        )
        with db_session():
            from api.Modules.Audit.Models import SuperadminAuditLog
            row = (
                db.session.query(SuperadminAuditLog)
                .filter_by(action="reply_support_ticket", target_id=str(tid))
                .first()
            )
            assert row is not None

    def test_user_reply_writes_operator_audit(self, client, admin_headers):
        tid = _make_ticket(client, admin_headers)
        client.post(
            f"/api/v2/tickets/{tid}/messages", headers=admin_headers,
            json={"body": "audited too"},
        )
        with db_session():
            from api.Modules.Audit.Models import OperatorAuditLog
            row = (
                db.session.query(OperatorAuditLog)
                .filter_by(action="reply_support_ticket", target_id=str(tid))
                .first()
            )
            assert row is not None
