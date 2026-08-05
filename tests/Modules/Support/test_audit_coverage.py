"""Regression guard for CLAUDE.md invariant #7 — the admin/
superadmin `PUT /tickets/{id}` mutation records an audit row.

Actor split: a superadmin edits any store's ticket and carries no
store_id claim, so the row lands in `SuperadminAuditLog`; a store
admin lands in that store's `OperatorAuditLog` (pinned to the
ticket's store). Both paths are covered here.

(`POST /tickets` is deliberately NOT audited — it's a self-service
user submission, not an operator/superadmin admin mutation, so it
falls outside invariant #7.)
"""
import pytest
from tests._app import db, db_session
from tests.conftest import login_admin, login_superadmin


@pytest.fixture
def admin_store_id():
    with db_session():
        from api.Modules.Tenancy.Models import Store
        return db.session.query(Store).first().id


def _seed_ticket(store_id):
    from api.Modules.Support.Models import SupportTicket
    with db_session():
        t = SupportTicket(
            store_id=store_id, user_id=1, submitted_by="admin@test.com",
            category="bug", subject="Broken thing", body="Details.",
            status="open", priority="normal",
        )
        db.session.add(t); db.session.commit()
        return t.id


def test_update_ticket_by_admin_emits_operator_audit(client, admin_store_id):
    from api.Modules.Audit.Models import OperatorAuditLog
    ticket_id = _seed_ticket(admin_store_id)
    token = login_admin(client, admin_store_id)
    resp = client.put(
        f"/api/v2/tickets/{ticket_id}",
        json={"status": "resolved", "admin_reply": "Fixed in the next build."},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, resp.get_data(as_text=True)
    row = (
        db.session.query(OperatorAuditLog)
          .filter_by(store_id=admin_store_id, action="update_support_ticket")
          .order_by(OperatorAuditLog.id.desc())
          .first()
    )
    assert row is not None
    assert row.target_type == "support_ticket"
    assert row.target_id == str(ticket_id)
    assert "status=resolved" in (row.summary or "")
    assert "reply=yes" in (row.summary or "")


def test_update_ticket_by_superadmin_emits_superadmin_audit(
    client, admin_store_id,
):
    from api.Modules.Audit.Models import SuperadminAuditLog
    ticket_id = _seed_ticket(admin_store_id)
    token = login_superadmin(client)
    resp = client.put(
        f"/api/v2/tickets/{ticket_id}",
        json={"priority": "P1"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, resp.get_data(as_text=True)
    row = (
        db.session.query(SuperadminAuditLog)
          .filter_by(action="update_support_ticket")
          .order_by(SuperadminAuditLog.id.desc())
          .first()
    )
    assert row is not None
    assert row.target_type == "support_ticket"
    assert row.target_id == str(ticket_id)
    assert "priority=P1" in (row.details or "")
