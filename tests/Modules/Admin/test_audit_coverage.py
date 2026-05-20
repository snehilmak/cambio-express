"""Regression guard for CLAUDE.md invariant #7 — every mutating
admin/owner endpoint records an `OperatorAuditLog` row.

This file was born from a real gap: `test_employee_action_audit.py`
once covered roster mutations but got deleted somewhere along the
way, and the controllers' audit calls drifted out with it.  Five
admin routes + one owner route silently mutated state without
emitting an audit row by the time this PR landed.  Keep these
tests green to keep the audit trail honest.

If a future refactor moves a Service-layer mutation off the
controller, port the audit emission alongside or this test fires.
"""
from tests._app import db, db_session


def _login_admin(client, store_id):
    resp = client.post(
        "/api/v2/auth/login",
        json={
            "username": "admin@test.com",
            "password": "testpass123!",
            "store_id": store_id,
        },
    )
    return resp.get_json()["access_token"]


def _set_paid_plan(store_id, plan="basic"):
    from api.Modules.Tenancy.Models import Store
    with db_session():
        s = db.session.query(Store).filter_by(id=store_id).first()
        s.plan = plan
        db.session.commit()


def _latest_audit_row(store_id, action: str):
    """Return the most recent OperatorAuditLog row matching
    (store_id, action), or None."""
    from api.Modules.Audit.Models import OperatorAuditLog
    return (
        db.session.query(OperatorAuditLog)
          .filter_by(store_id=store_id, action=action)
          .order_by(OperatorAuditLog.id.desc())
          .first()
    )


# ── Admin: store info ───────────────────────────────────────


def test_update_store_info_emits_audit_row(client, test_store_id):
    """`PUT /admin/store-info` records an `update_store_info`
    operator-audit row listing the fields the operator touched."""
    token = _login_admin(client, test_store_id)
    resp = client.put(
        "/api/v2/admin/store-info",
        json={"federal_tax_rate": 0.08},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    row = _latest_audit_row(test_store_id, "update_store_info")
    assert row is not None, "expected an update_store_info audit row"
    assert "federal_tax_rate" in (row.summary or "")
    assert row.target_type == "store"
    assert row.target_id == str(test_store_id)


def test_update_store_info_no_op_skips_audit(client, test_store_id):
    """An empty-body update is a no-op — no audit row is emitted.
    Matches the superadmin update_store_route pattern: only the
    audit emission is gated on `if changed:`, not the route
    itself."""
    token = _login_admin(client, test_store_id)
    # Snapshot pre-call count so the no-op doesn't appear.
    from api.Modules.Audit.Models import OperatorAuditLog
    before = (
        db.session.query(OperatorAuditLog)
          .filter_by(store_id=test_store_id, action="update_store_info")
          .count()
    )
    resp = client.put(
        "/api/v2/admin/store-info",
        json={},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    after = (
        db.session.query(OperatorAuditLog)
          .filter_by(store_id=test_store_id, action="update_store_info")
          .count()
    )
    assert after == before


# ── Admin: team roster ──────────────────────────────────────


def test_create_team_member_emits_audit_row(client, test_store_id):
    token = _login_admin(client, test_store_id)
    resp = client.post(
        "/api/v2/admin/team",
        json={"name": "Audit-Test Cashier", "hourly_rate": 15.0},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201
    row = _latest_audit_row(test_store_id, "create_team_member")
    assert row is not None
    assert "Audit-Test Cashier" in (row.target_label or "")


def test_update_team_member_emits_rename_audit(client, test_store_id):
    token = _login_admin(client, test_store_id)
    create = client.post(
        "/api/v2/admin/team",
        json={"name": "Pre-Rename", "hourly_rate": 0.0},
        headers={"Authorization": f"Bearer {token}"},
    )
    employee_id = create.get_json()["id"]
    resp = client.put(
        f"/api/v2/admin/team/{employee_id}",
        json={"name": "Post-Rename"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    row = _latest_audit_row(test_store_id, "update_team_member")
    assert row is not None
    assert "name" in (row.summary or "")


def test_update_team_member_emits_reactivate_action(client, test_store_id):
    """Reactivation gets its own action label so the audit feed
    distinguishes "fired" vs "rehired" at a glance."""
    token = _login_admin(client, test_store_id)
    create = client.post(
        "/api/v2/admin/team",
        json={"name": "Boomerang Cashier"},
        headers={"Authorization": f"Bearer {token}"},
    )
    employee_id = create.get_json()["id"]
    # Deactivate first so reactivation is the operation under test.
    client.delete(
        f"/api/v2/admin/team/{employee_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    resp = client.put(
        f"/api/v2/admin/team/{employee_id}",
        json={"is_active": True},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    row = _latest_audit_row(test_store_id, "reactivate_team_member")
    assert row is not None


def test_deactivate_team_member_emits_audit_row(client, test_store_id):
    token = _login_admin(client, test_store_id)
    create = client.post(
        "/api/v2/admin/team",
        json={"name": "Goodbye Cashier"},
        headers={"Authorization": f"Bearer {token}"},
    )
    employee_id = create.get_json()["id"]
    resp = client.delete(
        f"/api/v2/admin/team/{employee_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 204
    row = _latest_audit_row(test_store_id, "deactivate_team_member")
    assert row is not None


# ── Admin: subscription add-ons ─────────────────────────────


def test_toggle_addon_emits_enabled_then_disabled(client, test_store_id):
    _set_paid_plan(test_store_id, "basic")
    token = _login_admin(client, test_store_id)
    # First flip — on.
    client.post(
        "/api/v2/admin/addons/tv_display/toggle",
        headers={"Authorization": f"Bearer {token}"},
    )
    enabled = _latest_audit_row(test_store_id, "addon_enabled")
    assert enabled is not None
    assert enabled.target_id == "tv_display"
    # Second flip — off.  Distinct action label so the audit feed
    # shows both events as separate rows.
    client.post(
        "/api/v2/admin/addons/tv_display/toggle",
        headers={"Authorization": f"Bearer {token}"},
    )
    disabled = _latest_audit_row(test_store_id, "addon_disabled")
    assert disabled is not None
    assert disabled.target_id == "tv_display"


# ── Owner: unlink store ─────────────────────────────────────


def test_owner_unlink_store_emits_audit_row(client, test_store_id):
    """Disconnecting a store from the owner umbrella materially
    changes who can see it — the affected store's admin audit feed
    should show that an owner unlinked them."""
    from api.Modules.Tenancy.Models import StoreOwnerLink, User
    # Seed an owner + a link to the test store.
    with db_session():
        owner = User(
            store_id=None, username="audit_owner@test.com",
            full_name="Audit Test Owner", role="owner",
        )
        owner.set_password("ownerpass123!")
        db.session.add(owner); db.session.flush()
        link = StoreOwnerLink(owner_id=owner.id, store_id=test_store_id)
        db.session.add(link); db.session.commit()
        owner_id = owner.id

    login = client.post(
        "/api/v2/auth/login",
        json={
            "username": "audit_owner@test.com",
            "password": "ownerpass123!",
        },
    )
    assert login.status_code == 200, login.get_data(as_text=True)
    token = login.get_json()["access_token"]

    resp = client.post(
        f"/api/v2/owner/unlink/{test_store_id}",
        json={},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 204
    row = _latest_audit_row(test_store_id, "owner_unlink_store")
    assert row is not None
    assert row.user_id == owner_id
    assert row.target_type == "store_owner_link"
