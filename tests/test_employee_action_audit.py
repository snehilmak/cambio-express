"""Employee-action audit coverage tests.

The "Before going live" item "Employee action audit" wired
``record_op_audit`` into every mutating route under
``blueprints/bookkeeping_mutations.py`` (return-checks) and
``blueprints/admin_settings_mutations.py`` (roster / team / owner).
These tests exercise each route and assert an ``OperatorAuditLog``
row landed with the expected target_type + action.

When a NEW mutating route is added on the store-admin / employee
side, add a case here so the regression guard catches a missing
``record_op_audit`` call.
"""
from __future__ import annotations

import pytest


def _audit_rows(store_id, *, target_type=None, action=None):
    """Fetch OperatorAuditLog rows for the given store, optionally
    filtered by target_type / action."""
    from app import OperatorAuditLog
    q = OperatorAuditLog.query.filter_by(store_id=store_id)
    if target_type is not None:
        q = q.filter_by(target_type=target_type)
    if action is not None:
        q = q.filter_by(action=action)
    return q.order_by(OperatorAuditLog.id.desc()).all()


# ── Return-checks (8 mutations) ──────────────────────────────────

def test_return_check_new_writes_audit(
    logged_in_client, test_store_id,
):
    client = logged_in_client
    r = client.post(
        "/return-checks/new",
        data={
            "bounced_on": "2026-05-01",
            "customer_name": "Alice Test",
            "amount": "150.00",
        },
        follow_redirects=False,
    )
    assert r.status_code in (302, 303), r.status_code
    rows = _audit_rows(
        test_store_id, target_type="return_check", action="create",
    )
    assert len(rows) >= 1
    assert "Alice Test" in rows[0].target_label


def test_return_check_payment_writes_audit(
    logged_in_client, test_store_id,
):
    client = logged_in_client
    # Create the return-check first.
    client.post(
        "/return-checks/new",
        data={
            "bounced_on": "2026-05-02",
            "customer_name": "Bob Pays",
            "amount": "100.00",
        },
    )
    from app import ReturnCheck
    rc = ReturnCheck.query.filter_by(
        store_id=test_store_id, customer_name="Bob Pays",
    ).first()
    assert rc is not None

    r = client.post(
        f"/return-checks/{rc.id}/payment",
        data={
            "amount": "40.00", "paid_on": "2026-05-05",
            "payment_method": "cash",
        },
    )
    assert r.status_code in (302, 303), r.status_code
    rows = _audit_rows(
        test_store_id, target_type="return_check", action="payment",
    )
    assert len(rows) >= 1
    assert "$40.00" in rows[0].summary


def test_return_check_loss_writes_audit(
    logged_in_client, test_store_id,
):
    client = logged_in_client
    client.post(
        "/return-checks/new",
        data={
            "bounced_on": "2026-05-03",
            "customer_name": "Carol Loss",
            "amount": "200.00",
        },
    )
    from app import ReturnCheck
    rc = ReturnCheck.query.filter_by(
        store_id=test_store_id, customer_name="Carol Loss",
    ).first()
    client.post(
        f"/return-checks/{rc.id}/loss",
        data={"status_changed_on": "2026-05-10"},
    )
    rows = _audit_rows(
        test_store_id, target_type="return_check", action="mark_loss",
    )
    assert len(rows) >= 1
    assert "Carol Loss" in rows[0].target_label


def test_return_check_delete_writes_audit(
    logged_in_client, test_store_id,
):
    client = logged_in_client
    client.post(
        "/return-checks/new",
        data={
            "bounced_on": "2026-05-04",
            "customer_name": "Dave Drop",
            "amount": "50.00",
        },
    )
    from app import ReturnCheck
    rc = ReturnCheck.query.filter_by(
        store_id=test_store_id, customer_name="Dave Drop",
    ).first()
    rc_id = rc.id
    client.post(f"/return-checks/{rc_id}/delete")
    rows = _audit_rows(
        test_store_id, target_type="return_check", action="delete",
    )
    # The audit row records the deleted rc's id + label.
    assert any(r.target_id == str(rc_id) for r in rows), [
        (r.action, r.target_id) for r in rows
    ]


# ── Roster (3 mutations) ─────────────────────────────────────────

def test_roster_add_writes_audit(
    logged_in_client, test_store_id,
):
    client = logged_in_client
    client.post(
        "/admin/settings/roster/add",
        data={"name": "Eve Roster"},
    )
    rows = _audit_rows(
        test_store_id, target_type="roster_member", action="create",
    )
    assert any(r.target_label == "Eve Roster" for r in rows), [
        (r.action, r.target_label) for r in rows
    ]


def test_roster_toggle_writes_audit(
    logged_in_client, test_store_id,
):
    client = logged_in_client
    client.post(
        "/admin/settings/roster/add",
        data={"name": "Fred Toggle"},
    )
    from app import StoreEmployee
    emp = StoreEmployee.query.filter_by(
        store_id=test_store_id, name="Fred Toggle",
    ).first()
    client.post(f"/admin/settings/roster/{emp.id}/toggle")
    rows = _audit_rows(
        test_store_id, target_type="roster_member",
    )
    actions = {r.action for r in rows if r.target_id == str(emp.id)}
    # Should have both create and a toggle action.
    assert "create" in actions
    assert ("deactivate" in actions) or ("reactivate" in actions)


def test_roster_rename_writes_audit(
    logged_in_client, test_store_id,
):
    client = logged_in_client
    client.post(
        "/admin/settings/roster/add",
        data={"name": "Grace Old"},
    )
    from app import StoreEmployee
    emp = StoreEmployee.query.filter_by(
        store_id=test_store_id, name="Grace Old",
    ).first()
    client.post(
        f"/admin/settings/roster/{emp.id}/rename",
        data={"name": "Grace New"},
    )
    rows = _audit_rows(
        test_store_id, target_type="roster_member", action="rename",
    )
    assert any(r.target_id == str(emp.id) for r in rows)
    rename_row = next(
        r for r in rows if r.target_id == str(emp.id)
    )
    assert "Grace Old" in rename_row.summary
    assert "Grace New" in rename_row.summary
