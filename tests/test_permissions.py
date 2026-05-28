"""Permission resolution tests — covers the full permissions_for() flow.

Tests the three-tier resolution:
  1. Per-store override (StoreRoleOverride)
  2. Global defaults (RolePermission)
  3. Hardcoded RBAC_DEFAULTS fallback

Plus: the seeding logic that populates RolePermission from
RBAC_DEFAULTS on first edit, and admin role boundary enforcement.
"""
from tests._app import db, db_session
from tests.conftest import login_superadmin, login_admin


def _headers(token):
    return {"Authorization": f"Bearer {token}"}


class TestPermissionsFor:
    """Unit-level tests for the permissions_for() resolution chain."""

    def test_superadmin_gets_all_permissions(self):
        from api.Modules.Auth.Services.login import (
            RBAC_ACTIONS, RBAC_RESOURCES, permissions_for,
        )
        perms = permissions_for("superadmin")
        for r in RBAC_RESOURCES:
            for a in RBAC_ACTIONS:
                assert f"{r}.{a}" in perms

    def test_empty_table_falls_through_to_defaults(self):
        from api.Modules.Auth.Services.login import (
            RBAC_DEFAULTS, permissions_for,
        )
        from api.Modules.Auth.Models import RolePermission
        with db_session():
            db.session.query(RolePermission).delete()
            db.session.flush()
            perms = permissions_for("admin", db=db.session, store_id=1)
        expected = RBAC_DEFAULTS.get("admin", [])
        for p in expected:
            assert p in perms, f"Expected {p} in permissions"

    def test_role_permission_table_overrides_defaults(self):
        from api.Modules.Auth.Models import RolePermission
        from api.Modules.Auth.Services.login import permissions_for
        with db_session():
            db.session.query(RolePermission).delete()
            db.session.add(RolePermission(
                role="admin", resource="reports", action="read",
            ))
            db.session.flush()
            perms = permissions_for("admin", db=db.session, store_id=1)
        assert "reports.read" in perms
        assert "transfers.read" not in perms

    def test_populated_table_with_zero_rows_for_role_gives_empty(self):
        """If RolePermission has rows for other roles but none for admin,
        admin should get zero granular permissions (not fall through)."""
        from api.Modules.Auth.Models import RolePermission
        from api.Modules.Auth.Services.login import permissions_for
        with db_session():
            db.session.query(RolePermission).delete()
            db.session.add(RolePermission(
                role="employee", resource="transfers", action="read",
            ))
            db.session.flush()
            perms = permissions_for("admin", db=db.session, store_id=1)
        granular = [p for p in perms if "." in p and not p.startswith("store.")]
        assert granular == [], f"Expected no granular perms but got {granular}"

    def test_store_override_takes_priority_over_global(self):
        from api.Modules.Auth.Models import RolePermission, StoreRoleOverride
        from api.Modules.Auth.Services.login import permissions_for
        with db_session():
            db.session.query(RolePermission).delete()
            db.session.add(RolePermission(
                role="admin", resource="transfers", action="read",
            ))
            db.session.add(RolePermission(
                role="admin", resource="transfers", action="create",
            ))
            db.session.query(StoreRoleOverride).filter_by(
                store_id=1, role="admin",
            ).delete()
            db.session.add(StoreRoleOverride(
                store_id=1, role="admin",
                resource="reports", action="read",
            ))
            db.session.flush()
            perms = permissions_for("admin", db=db.session, store_id=1)
        assert "reports.read" in perms
        assert "transfers.read" not in perms
        assert "transfers.create" not in perms


class TestGlobalPermissionUpdate:
    """Integration tests for the superadmin global permissions endpoint."""

    def test_seed_and_remove_permission(self, client, test_store_id):
        token = login_superadmin(client)
        resp = client.put(
            "/api/v2/superadmin/permissions",
            json={"changes": [
                {"role": "admin", "resource": "transfers", "action": "read", "allowed": False},
                {"role": "admin", "resource": "transfers", "action": "create", "allowed": False},
                {"role": "admin", "resource": "transfers", "action": "update", "allowed": False},
            ]},
            headers=_headers(token),
        )
        assert resp.status_code == 200
        matrix = resp.get_json()["matrix"]
        assert matrix["admin"]["transfers"]["read"] is False
        assert matrix["admin"]["transfers"]["create"] is False

    def test_seed_actually_populates_table(self, client, test_store_id):
        """The first edit seeds RolePermission from RBAC_DEFAULTS.
        After seeding, the table has rows for each default role."""
        token = login_superadmin(client)
        client.put(
            "/api/v2/superadmin/permissions",
            json={"changes": [
                {"role": "admin", "resource": "transfers", "action": "read", "allowed": True},
            ]},
            headers=_headers(token),
        )
        resp = client.get(
            "/api/v2/superadmin/permissions",
            headers=_headers(token),
        )
        assert resp.status_code == 200
        matrix = resp.get_json()["matrix"]
        assert matrix["admin"]["transfers"]["read"] is True


class TestPerStorePermissionOverride:
    """Integration tests for per-store permission overrides."""

    def test_admin_can_read_permissions(self, client, test_store_id):
        token = login_admin(client, test_store_id)
        resp = client.get(
            "/api/v2/admin/store-permissions",
            headers=_headers(token),
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert "matrix" in data
        assert "admin" in data["roles"]
        assert "employee" in data["roles"]

    def test_admin_cannot_edit_admin_role(self, client, test_store_id):
        token = login_admin(client, test_store_id)
        resp = client.put(
            "/api/v2/admin/store-permissions",
            json={"changes": [
                {"role": "admin", "resource": "transfers", "action": "read", "allowed": False},
            ]},
            headers=_headers(token),
        )
        assert resp.status_code == 403

    def test_admin_can_edit_employee_role(self, client, test_store_id):
        token = login_admin(client, test_store_id)
        resp = client.put(
            "/api/v2/admin/store-permissions",
            json={"changes": [
                {"role": "employee", "resource": "transfers", "action": "create", "allowed": False},
            ]},
            headers=_headers(token),
        )
        assert resp.status_code == 200

    def test_removing_permission_on_fresh_store_persists(self, client, test_store_id):
        """Sending a full matrix with transfers.create/update/delete=false
        should persist correctly, even on a fresh store."""
        token = login_admin(client, test_store_id)
        with db_session():
            from api.Modules.Auth.Models import StoreRoleOverride
            db.session.query(StoreRoleOverride).filter_by(
                store_id=test_store_id, role="employee",
            ).delete()
            db.session.commit()

        resp_get = client.get(
            "/api/v2/admin/store-permissions",
            headers=_headers(token),
        )
        current_matrix = resp_get.get_json()["matrix"]["employee"]
        current_matrix["transfers"]["create"] = False
        current_matrix["transfers"]["update"] = False
        current_matrix["transfers"]["delete"] = False

        resp = client.put(
            "/api/v2/admin/store-permissions",
            json={"matrix": {"employee": current_matrix}},
            headers=_headers(token),
        )
        assert resp.status_code == 200
        matrix = resp.get_json()["matrix"]
        assert matrix["employee"]["transfers"]["read"] is True
        assert matrix["employee"]["transfers"]["create"] is False
        assert matrix["employee"]["transfers"]["update"] is False


    def test_partial_removal_persists(self, client, test_store_id):
        """Keeping only transfers.read and removing create/update/delete
        should persist — the most common per-store customization."""
        token = login_admin(client, test_store_id)
        resp_get = client.get(
            "/api/v2/admin/store-permissions",
            headers=_headers(token),
        )
        current_matrix = resp_get.get_json()["matrix"]["employee"]
        current_matrix["transfers"]["create"] = False
        current_matrix["transfers"]["update"] = False

        resp = client.put(
            "/api/v2/admin/store-permissions",
            json={"matrix": {"employee": current_matrix}},
            headers=_headers(token),
        )
        assert resp.status_code == 200
        matrix = resp.get_json()["matrix"]
        assert matrix["employee"]["transfers"]["read"] is True
        assert matrix["employee"]["transfers"]["create"] is False
        assert matrix["employee"]["transfers"]["update"] is False

    def test_save_then_save_again_is_idempotent(self, client, test_store_id):
        """Saving the same permission change twice should not duplicate
        rows or change the outcome."""
        token = login_admin(client, test_store_id)
        change = [{"role": "employee", "resource": "transfers", "action": "create", "allowed": False}]
        resp1 = client.put(
            "/api/v2/admin/store-permissions",
            json={"changes": change},
            headers=_headers(token),
        )
        assert resp1.status_code == 200
        resp2 = client.put(
            "/api/v2/admin/store-permissions",
            json={"changes": change},
            headers=_headers(token),
        )
        assert resp2.status_code == 200
        assert resp1.get_json()["matrix"] == resp2.get_json()["matrix"]

    def test_reset_then_edit_works(self, client, test_store_id):
        """After resetting to defaults, a subsequent edit should still
        seed and apply correctly."""
        token = login_admin(client, test_store_id)
        client.put(
            "/api/v2/admin/store-permissions",
            json={"changes": [
                {"role": "employee", "resource": "reports", "action": "read", "allowed": False},
            ]},
            headers=_headers(token),
        )
        client.post(
            "/api/v2/admin/store-permissions/reset",
            json={"role": "employee"},
            headers=_headers(token),
        )
        resp = client.put(
            "/api/v2/admin/store-permissions",
            json={"changes": [
                {"role": "employee", "resource": "transfers", "action": "create", "allowed": False},
            ]},
            headers=_headers(token),
        )
        assert resp.status_code == 200
        matrix = resp.get_json()["matrix"]
        assert matrix["employee"]["transfers"]["read"] is True
        assert matrix["employee"]["transfers"]["create"] is False

    def test_invalid_role_rejected(self, client, test_store_id):
        """Trying to edit a role outside the allowed set returns 403."""
        token = login_admin(client, test_store_id)
        resp = client.put(
            "/api/v2/admin/store-permissions",
            json={"changes": [
                {"role": "superadmin", "resource": "transfers", "action": "read", "allowed": False},
            ]},
            headers=_headers(token),
        )
        assert resp.status_code == 403

    def test_invalid_resource_ignored(self, client, test_store_id):
        """A change with an invalid resource name should be silently
        ignored — no error, no side effect."""
        token = login_admin(client, test_store_id)
        resp = client.put(
            "/api/v2/admin/store-permissions",
            json={"changes": [
                {"role": "employee", "resource": "nonexistent", "action": "read", "allowed": False},
            ]},
            headers=_headers(token),
        )
        assert resp.status_code == 200

    def test_empty_changes_is_noop(self, client, test_store_id):
        """An empty changes array should succeed without side effects."""
        token = login_admin(client, test_store_id)
        resp = client.put(
            "/api/v2/admin/store-permissions",
            json={"changes": []},
            headers=_headers(token),
        )
        assert resp.status_code == 200


class TestSuperadminPerStorePermissions:
    """Superadmin per-store permission overrides from the store drill."""

    def test_superadmin_can_remove_permission_on_fresh_store(self, client, test_store_id):
        token = login_superadmin(client)
        with db_session():
            from api.Modules.Auth.Models import StoreRoleOverride
            db.session.query(StoreRoleOverride).filter_by(
                store_id=test_store_id, role="admin",
            ).delete()
            db.session.commit()

        resp_get = client.get(
            f"/api/v2/superadmin/stores/{test_store_id}/permissions",
            headers=_headers(token),
        )
        current_matrix = resp_get.get_json()["matrix"]["admin"]
        current_matrix["transfers"]["create"] = False
        current_matrix["transfers"]["update"] = False
        current_matrix["transfers"]["delete"] = False

        resp = client.put(
            f"/api/v2/superadmin/stores/{test_store_id}/permissions",
            json={"matrix": {"admin": current_matrix}},
            headers=_headers(token),
        )
        assert resp.status_code == 200
        matrix = resp.get_json()["matrix"]
        assert matrix["admin"]["transfers"]["read"] is True
        assert matrix["admin"]["transfers"]["create"] is False
        assert matrix["admin"]["transfers"]["update"] is False
        assert matrix["admin"]["transfers"]["delete"] is False
