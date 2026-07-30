"""Regression guard for CLAUDE.md invariant #7 — every mutating
ReturnChecks endpoint records an `OperatorAuditLog` row.

ReturnChecks is the financial-recovery surface (money the store is
clawing back after a bounced check), so every state change matters
for reconciliation.  Until this sweep landed, the seven mutation
routes silently mutated state — these tests fire if a future
refactor moves the audit emission off the controllers.
"""
from datetime import date

from tests._app import db, db_session


def _login(client, store_id):
    resp = client.post(
        "/api/v2/auth/login",
        json={
            "username": "admin@test.com",
            "password": "testpass123!",
            "store_id": store_id,
        },
    )
    return resp.get_json()["access_token"]


def _seed_rc(store_id, *, customer_name="Bouncer Co",
             amount=500.0, status="pending"):
    from api.Modules.ReturnChecks.Models import ReturnCheck
    r = ReturnCheck(
        store_id=store_id,
        bounced_on=date.today(),
        customer_name=customer_name,
        check_number="123",
        payer_bank="Bank A",
        amount=amount,
        status=status,
    )
    db.session.add(r); db.session.commit()
    return r.id


def _latest_audit(store_id, action: str):
    from api.Modules.Audit.Models import OperatorAuditLog
    return (
        db.session.query(OperatorAuditLog)
          .filter_by(store_id=store_id, action=action)
          .order_by(OperatorAuditLog.id.desc())
          .first()
    )


# ── POST + PUT — parent CRUD ────────────────────────────────


def test_create_return_check_emits_audit_row(client, test_store_id):
    token = _login(client, test_store_id)
    resp = client.post(
        "/api/v2/return-checks",
        json={
            "bounced_on":    date.today().isoformat(),
            "customer_name": "Audit Customer",
            "company_name":  "Audit Co",
            "check_number":  "999",
            "payer_bank":    "Bank Z",
            "amount":        250.0,
            "notes":         "audit smoke",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201, resp.get_data(as_text=True)
    row = _latest_audit(test_store_id, "create_return_check")
    assert row is not None
    assert "Audit Customer" in (row.target_label or "")
    summary = row.summary or ""
    assert "999" in summary
    assert "250.00" in summary


def test_update_return_check_emits_audit_row(client, test_store_id):
    rc_id = _seed_rc(test_store_id, customer_name="Pre-Rename")
    token = _login(client, test_store_id)
    resp = client.put(
        f"/api/v2/return-checks/{rc_id}",
        json={
            "bounced_on":    date.today().isoformat(),
            "customer_name": "Post-Rename",
            "company_name":  "Post Co",
            "check_number":  "456",
            "payer_bank":    "Bank A",
            "amount":        500.0,
            "notes":         "",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    row = _latest_audit(test_store_id, "update_return_check")
    assert row is not None
    assert "Post-Rename" in (row.target_label or "")


# ── POST /{id}/mark-loss | mark-fraud | reopen ──────────────


def test_mark_loss_emits_audit_row(client, test_store_id):
    rc_id = _seed_rc(test_store_id)
    token = _login(client, test_store_id)
    resp = client.post(
        f"/api/v2/return-checks/{rc_id}/mark-loss",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    row = _latest_audit(test_store_id, "mark_loss")
    assert row is not None
    assert "loss" in (row.summary or "")


def test_mark_fraud_emits_audit_row(client, test_store_id):
    rc_id = _seed_rc(test_store_id)
    token = _login(client, test_store_id)
    resp = client.post(
        f"/api/v2/return-checks/{rc_id}/mark-fraud",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    row = _latest_audit(test_store_id, "mark_fraud")
    assert row is not None
    assert "fraud" in (row.summary or "")


def test_reopen_emits_audit_row(client, test_store_id):
    rc_id = _seed_rc(test_store_id, status="loss")
    token = _login(client, test_store_id)
    resp = client.post(
        f"/api/v2/return-checks/{rc_id}/reopen",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    row = _latest_audit(test_store_id, "reopen_return_check")
    assert row is not None
    assert "pending" in (row.summary or "")


# ── POST + DELETE /{id}/payments ────────────────────────────


def test_record_payment_emits_audit_row(client, test_store_id):
    rc_id = _seed_rc(test_store_id, amount=500.0)
    token = _login(client, test_store_id)
    resp = client.post(
        f"/api/v2/return-checks/{rc_id}/payments",
        json={
            "paid_on": date.today().isoformat(),
            "amount":  100.0,
            "method":  "cash",
            "note":    "first installment",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201, resp.get_data(as_text=True)
    row = _latest_audit(test_store_id, "record_payment")
    assert row is not None
    assert row.target_type == "return_check_payment"
    summary = row.summary or ""
    assert f"rc={rc_id}" in summary
    assert "100.00" in summary


def test_delete_payment_emits_audit_row(client, test_store_id):
    rc_id = _seed_rc(test_store_id, amount=500.0)
    token = _login(client, test_store_id)
    create = client.post(
        f"/api/v2/return-checks/{rc_id}/payments",
        json={
            "paid_on": date.today().isoformat(),
            "amount":  75.0,
            "method":  "cash",
            "note":    "to be deleted",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    payment_id = create.get_json()["payment"]["id"]
    resp = client.delete(
        f"/api/v2/return-checks/{rc_id}/payments/{payment_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    row = _latest_audit(test_store_id, "delete_payment")
    assert row is not None
    # Delete-side audit captures the pre-delete amount so the
    # feed answers "we deleted payment #X — how much was that?".
    assert "75.00" in (row.summary or "")
