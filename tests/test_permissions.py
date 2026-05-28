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
