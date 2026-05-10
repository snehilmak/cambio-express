"""Tests for the OperatorAuditLog (Batch A.3a — Employee Action Audit).

Covers:
  - Audit rows are written for daily-report lock/unlock, batch
    create/update, and transfer delete
  - The /admin/audit-log page renders + filters
  - Employee role can't view the log (admin-only by decorator)
"""
from datetime import date


def _admin_login(client, store_id):
    from app import User, Store, db
    with client.application.app_context():
        u = User.query.filter_by(store_id=store_id, role="admin").first()
        uid = u.id
        s = db.session.get(Store, store_id)
        s.plan = "pro"
        db.session.commit()
    with client.session_transaction() as sess:
        sess["user_id"] = uid
        sess["role"] = "admin"
        sess["store_id"] = store_id


# ── Audit hooks fire ─────────────────────────────────────────


def _admin_jwt_early(client, test_store_id):
    """Mint a Bearer JWT for the admin (used by daily-lock + batch
    audit tests below). Defined here so the daily-lock tests can
    use it without forward-reference."""
    resp = client.post(
        "/api/v2/auth/login",
        json={"username": "admin@test.com",
              "password": "testpass123!",
              "store_id": test_store_id},
    )
    return resp.get_json()["access_token"]


def test_daily_report_lock_writes_audit(client, test_store_id):
    """The legacy /daily/<ds>/lock POST is gone (PR #403); the SPA
    POSTs to /api/v2/daily/<store>/<date>/lock. Audit-log invariant
    moved with it — every state transition (was-not-locked → locked)
    still appends an OperatorAuditLog row."""
    _admin_login(client, test_store_id)
    token = _admin_jwt_early(client, test_store_id)
    today = date.today().isoformat()
    resp = client.post(
        f"/api/v2/daily/{test_store_id}/{today}/lock",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, resp.get_data(as_text=True)
    from app import OperatorAuditLog, app as flask_app
    with flask_app.app_context():
        rows = OperatorAuditLog.query.filter_by(
            store_id=test_store_id, action="lock").all()
        assert len(rows) == 1
        assert rows[0].target_type == "daily_report"
        assert today in rows[0].target_label


def test_daily_report_unlock_writes_audit(client, test_store_id):
    """Same migration as lock: SPA POSTs to /api/v2/daily/.../unlock,
    audit row lands on that side."""
    _admin_login(client, test_store_id)
    token = _admin_jwt_early(client, test_store_id)
    today = date.today().isoformat()
    headers = {"Authorization": f"Bearer {token}"}
    client.post(f"/api/v2/daily/{test_store_id}/{today}/lock", headers=headers)
    client.post(f"/api/v2/daily/{test_store_id}/{today}/unlock", headers=headers)
    from app import OperatorAuditLog, app as flask_app
    with flask_app.app_context():
        actions = [r.action for r in OperatorAuditLog.query.filter_by(
            store_id=test_store_id, target_type="daily_report").all()]
        assert "lock"   in actions
        assert "unlock" in actions


def _admin_jwt(client, test_store_id):
    """Mint a Bearer JWT for the admin so the SPA-side write
    endpoints accept the call. The legacy session-based admin
    login still applies for Flask routes; this gives us the
    matching API-side auth."""
    resp = client.post(
        "/api/v2/auth/login",
        json={"username": "admin@test.com",
              "password": "testpass123!",
              "store_id": test_store_id},
    )
    return resp.get_json()["access_token"]


def test_new_batch_writes_create_audit(client, test_store_id):
    """The legacy /batches/new POST is gone; the SPA POSTs to
    /api/v2/batches. The audit-log invariant moved with it: every
    batch create still appends an OperatorAuditLog row."""
    _admin_login(client, test_store_id)
    token = _admin_jwt(client, test_store_id)
    resp = client.post(
        "/api/v2/batches",
        json={
            "ach_date":   date.today().isoformat(),
            "company":    "Intermex",
            "batch_ref":  "B-001",
            "ach_amount": 1000.00,
            "status":     "Pending",
            "transfer_dates": "",
            "reconciled": False,
            "notes": "",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201, resp.get_data(as_text=True)
    from app import OperatorAuditLog, app as flask_app
    with flask_app.app_context():
        rows = OperatorAuditLog.query.filter_by(
            store_id=test_store_id, target_type="batch", action="create").all()
        assert len(rows) == 1
        assert "Intermex" in rows[0].target_label
        assert "B-001"    in rows[0].target_label


def test_edit_batch_writes_update_audit(client, test_store_id):
    """Same migration shape on the edit side: legacy form-POST
    handler 301'd; audit row now lands when the SPA PUTs to
    /api/v2/batches/<id>."""
    _admin_login(client, test_store_id)
    from app import ACHBatch, db, app as flask_app
    with flask_app.app_context():
        b = ACHBatch(store_id=test_store_id, ach_date=date.today(),
                     company="Maxi", batch_ref="B-EDIT",
                     ach_amount=500.0, status="Pending")
        db.session.add(b); db.session.commit()
        bid = b.id
    token = _admin_jwt(client, test_store_id)
    resp = client.put(
        f"/api/v2/batches/{bid}",
        json={
            "ach_date":   date.today().isoformat(),
            "company":    "Maxi",
            "batch_ref":  "B-EDIT",
            "ach_amount": 750.00,   # changed
            "status":     "Cleared",  # changed
            "transfer_dates": "",
            "reconciled": False,
            "notes": "",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, resp.get_data(as_text=True)
    from app import OperatorAuditLog
    with flask_app.app_context():
        rows = OperatorAuditLog.query.filter_by(
            store_id=test_store_id, target_type="batch", action="update").all()
        assert len(rows) == 1
        assert "amount" in rows[0].summary
        assert "status" in rows[0].summary


def test_delete_transfer_writes_audit(client, test_store_id):
    _admin_login(client, test_store_id)
    from app import Transfer, db, app as flask_app
    with flask_app.app_context():
        t = Transfer(
            store_id=test_store_id, send_date=date.today(),
            sender_name="DeleteMe Sender",
            recipient_name="DeleteMe Recipient",
            country="MX", confirm_number="DEL", company="Intermex",
            send_amount=999.0, fee=10.0, federal_tax=0.0, status="Sent",
        )
        db.session.add(t); db.session.commit()
        tid = t.id
    client.post(f"/transfers/{tid}/delete", follow_redirects=False)
    from app import OperatorAuditLog
    with flask_app.app_context():
        rows = OperatorAuditLog.query.filter_by(
            store_id=test_store_id, target_type="transfer", action="delete").all()
        assert len(rows) == 1
        assert "DeleteMe Sender" in rows[0].target_label


# ── /admin/audit-log page ────────────────────────────────────
#
# The page itself moved to React (/app/admin/audit-log). Filter +
# pagination behavior is exercised against the API endpoint in
# tests/Modules/Admin/test_audit_log_endpoint.py. What's left here
# is the legacy 301 redirect contract.


def test_audit_log_page_redirects_to_app(client, test_store_id):
    _admin_login(client, test_store_id)
    resp = client.get("/admin/audit-log", follow_redirects=False)
    assert resp.status_code == 301
    assert resp.headers["Location"].startswith("/app/admin/audit-log")


def test_audit_log_query_string_preserved_on_redirect(
    client, test_store_id,
):
    _admin_login(client, test_store_id)
    resp = client.get(
        "/admin/audit-log?target=batch&action=create",
        follow_redirects=False,
    )
    assert resp.status_code == 301
    location = resp.headers["Location"]
    assert "target=batch" in location
    assert "action=create" in location


def test_audit_log_employee_role_blocked(client, test_store_id):
    """Employees can't see the activity log — admin_required gates."""
    from app import User, db
    with client.application.app_context():
        u = User(username="cashier@audit.com", store_id=test_store_id,
                 role="employee", full_name="Cashier")
        u.set_password("p"); db.session.add(u); db.session.commit()
        uid = u.id
    with client.session_transaction() as sess:
        sess["user_id"] = uid
        sess["role"] = "employee"
        sess["store_id"] = test_store_id
    resp = client.get("/admin/audit-log", follow_redirects=False)
    assert resp.status_code != 200
