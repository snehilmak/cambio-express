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


def test_daily_report_lock_writes_audit(client, test_store_id):
    _admin_login(client, test_store_id)
    today = date.today().isoformat()
    resp = client.post(f"/daily/{today}/lock", follow_redirects=False)
    # 302 to the daily report page is success.
    assert resp.status_code in (200, 302)
    from app import OperatorAuditLog, app as flask_app
    with flask_app.app_context():
        rows = OperatorAuditLog.query.filter_by(
            store_id=test_store_id, action="lock").all()
        assert len(rows) == 1
        assert rows[0].target_type == "daily_report"
        assert today in rows[0].target_label


def test_daily_report_unlock_writes_audit(client, test_store_id):
    _admin_login(client, test_store_id)
    today = date.today().isoformat()
    client.post(f"/daily/{today}/lock")
    client.post(f"/daily/{today}/unlock")
    from app import OperatorAuditLog, app as flask_app
    with flask_app.app_context():
        actions = [r.action for r in OperatorAuditLog.query.filter_by(
            store_id=test_store_id, target_type="daily_report").all()]
        assert "lock"   in actions
        assert "unlock" in actions


def test_new_batch_writes_create_audit(client, test_store_id):
    _admin_login(client, test_store_id)
    resp = client.post("/batches/new", data={
        "ach_date":   date.today().isoformat(),
        "company":    "Intermex",
        "batch_ref":  "B-001",
        "ach_amount": "1000.00",
        "status":     "Pending",
    }, follow_redirects=False)
    assert resp.status_code in (200, 302)
    from app import OperatorAuditLog, app as flask_app
    with flask_app.app_context():
        rows = OperatorAuditLog.query.filter_by(
            store_id=test_store_id, target_type="batch", action="create").all()
        assert len(rows) == 1
        assert "Intermex" in rows[0].target_label
        assert "B-001"    in rows[0].target_label


def test_edit_batch_writes_update_audit(client, test_store_id):
    _admin_login(client, test_store_id)
    from app import ACHBatch, db, app as flask_app
    with flask_app.app_context():
        b = ACHBatch(store_id=test_store_id, ach_date=date.today(),
                     company="Maxi", batch_ref="B-EDIT",
                     ach_amount=500.0, status="Pending")
        db.session.add(b); db.session.commit()
        bid = b.id
    client.post(f"/batches/{bid}/edit", data={
        "ach_date":   date.today().isoformat(),
        "company":    "Maxi",
        "batch_ref":  "B-EDIT",
        "ach_amount": "750.00",   # changed
        "status":     "Cleared",  # changed
    })
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


def test_audit_log_page_renders(client, test_store_id):
    _admin_login(client, test_store_id)
    today = date.today().isoformat()
    client.post(f"/daily/{today}/lock")
    resp = client.get("/admin/audit-log")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "Activity Log" in body
    # The lock event we just generated should be visible.
    assert "lock" in body.lower()
    assert today in body


def test_audit_log_filters_by_target(client, test_store_id):
    _admin_login(client, test_store_id)
    # Seed two events of different target types.
    client.post(f"/daily/{date.today().isoformat()}/lock")
    client.post("/batches/new", data={
        "ach_date":   date.today().isoformat(),
        "company":    "Barri",
        "batch_ref":  "FILTER-TEST",
        "ach_amount": "100.00",
        "status":     "Pending",
    })
    # Filter to just batches.
    resp = client.get("/admin/audit-log?target=batch")
    body = resp.get_data(as_text=True)
    assert "FILTER-TEST" in body
    # Daily-report event shouldn't render in the batch-only view.
    # (We check the absence of the lock badge near the daily-report target.)
    # Pragmatic: just look for the daily-report target label.
    daily_label = f"Daily {date.today().isoformat()}"
    assert daily_label not in body


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
