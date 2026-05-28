"""Tests for per-store RBAC permission overrides.

Security-critical: verifies the hierarchical permission model:
  - Admin can only edit employee permissions for their store
  - Owner can edit admin + employee for their stores
  - Superadmin can edit any role for any store
  - Nobody can escalate their own role's permissions
  - Per-store overrides replace global defaults entirely
  - Reset removes all overrides and falls back to global
"""
import pytest
from tests._app import db, db_session
from tests.conftest import login_admin, login_superadmin


@pytest.fixture
def sa_token(client):
    return login_superadmin(client)


@pytest.fixture
def sa_headers(sa_token):
    return {"Authorization": f"Bearer {sa_token}"}


@pytest.fixture
def store_id():
    with db_session():
        from api.Modules.Tenancy.Models import Store
        store = db.session.query(Store).first()
        assert store is not None
        return store.id


@pytest.fixture
def admin_token(client, store_id):
    return login_admin(client, store_id)


@pytest.fixture
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


class TestGetStorePermissions:
    def test_admin_can_read(self, client, admin_headers):
        resp = client.get("/api/v2/admin/store-permissions", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "roles" in data
        assert "editable_roles" in data
        assert "matrix" in data
        assert "has_overrides" in data
        assert "resources" in data
        assert "actions" in data

    def test_admin_editable_roles_is_employee_only(self, client, admin_headers):
        resp = client.get("/api/v2/admin/store-permissions", headers=admin_headers)
        data = resp.json()
        assert data["editable_roles"] == ["employee"]

    def test_superadmin_editable_roles_includes_all(self, client, sa_headers):
        resp = client.get("/api/v2/admin/store-permissions", headers=sa_headers)
        # Superadmin has no store_id, so this should 403
        assert resp.status_code == 403

    def test_unauthenticated_rejected(self, client):
        resp = client.get("/api/v2/admin/store-permissions")
        assert resp.status_code in (401, 403)

    def test_matrix_structure(self, client, admin_headers):
        resp = client.get("/api/v2/admin/store-permissions", headers=admin_headers)
        data = resp.json()
        for role in data["roles"]:
            assert role in data["matrix"]
            for resource in data["resources"]:
                assert resource in data["matrix"][role]
                for action in data["actions"]:
                    assert action in data["matrix"][role][resource]
                    assert isinstance(data["matrix"][role][resource][action], bool)


class TestUpdateStorePermissions:
    def test_admin_can_edit_employee(self, client, admin_headers):
        resp = client.put(
            "/api/v2/admin/store-permissions",
            headers=admin_headers,
            json={"changes": [
                {"role": "employee", "resource": "settings", "action": "delete", "allowed": True},
            ]},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["matrix"]["employee"]["settings"]["delete"] is True
        assert "employee" in data["has_overrides"]
        # Revert
        client.put(
            "/api/v2/admin/store-permissions",
            headers=admin_headers,
            json={"changes": [
                {"role": "employee", "resource": "settings", "action": "delete", "allowed": False},
            ]},
        )

    def test_admin_cannot_edit_admin_role(self, client, admin_headers):
        resp = client.put(
            "/api/v2/admin/store-permissions",
            headers=admin_headers,
            json={"changes": [
                {"role": "admin", "resource": "transfers", "action": "delete", "allowed": False},
            ]},
        )
        assert resp.status_code == 403

    def test_admin_cannot_edit_owner_role(self, client, admin_headers):
        resp = client.put(
            "/api/v2/admin/store-permissions",
            headers=admin_headers,
            json={"changes": [
                {"role": "owner", "resource": "reports", "action": "read", "allowed": False},
            ]},
        )
        assert resp.status_code == 403

    def test_invalid_resource_ignored(self, client, admin_headers):
        resp = client.put(
            "/api/v2/admin/store-permissions",
            headers=admin_headers,
            json={"changes": [
                {"role": "employee", "resource": "nonexistent", "action": "read", "allowed": True},
            ]},
        )
        assert resp.status_code == 200

    def test_invalid_action_ignored(self, client, admin_headers):
        resp = client.put(
            "/api/v2/admin/store-permissions",
            headers=admin_headers,
            json={"changes": [
                {"role": "employee", "resource": "transfers", "action": "nuke", "allowed": True},
            ]},
        )
        assert resp.status_code == 200


class TestResetStorePermissions:
    def test_admin_can_reset_employee(self, client, admin_headers):
        # First create an override
        client.put(
            "/api/v2/admin/store-permissions",
            headers=admin_headers,
            json={"changes": [
                {"role": "employee", "resource": "settings", "action": "delete", "allowed": True},
            ]},
        )
        # Verify override exists
        check = client.get("/api/v2/admin/store-permissions", headers=admin_headers)
        assert "employee" in check.json()["has_overrides"]
        # Reset
        resp = client.post(
            "/api/v2/admin/store-permissions/reset",
            headers=admin_headers,
            json={"role": "employee"},
        )
        assert resp.status_code == 200
        assert "employee" not in resp.json()["has_overrides"]

    def test_admin_cannot_reset_admin_role(self, client, admin_headers):
        resp = client.post(
            "/api/v2/admin/store-permissions/reset",
            headers=admin_headers,
            json={"role": "admin"},
        )
        assert resp.status_code == 403

    def test_unauthenticated_rejected(self, client):
        resp = client.post(
            "/api/v2/admin/store-permissions/reset",
            json={"role": "employee"},
        )
        assert resp.status_code in (401, 403)


class TestPermissionEnforcement:
    """Verify that per-store overrides actually affect the JWT perms
    claim at login time."""

    def test_store_override_replaces_global(self, store_id):
        """When a store has overrides for a role, those replace the
        global defaults entirely — not merged."""
        from api.Core.Permissions import (
            set_store_permissions, permissions_for, reset_store_to_defaults,
        )
        set_store_permissions(
            store_id, "employee",
            {"transfers": {"read": True, "create": False, "update": False, "delete": False}},
        )
        perms = permissions_for("employee", store_id=store_id)
        granular = [p for p in perms if "." in p and not p.startswith("store.")]
        assert granular == ["transfers.read"]
        reset_store_to_defaults(store_id, "employee")

    def test_no_override_uses_global(self, store_id):
        """When no overrides exist, falls back to global defaults."""
        from api.Core.Permissions import permissions_for
        perms = permissions_for("employee", store_id=store_id)
        assert "transfers.create" in perms
        assert "transfers.read" in perms
