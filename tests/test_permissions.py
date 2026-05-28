"""Casbin permission system tests.

Covers the full resolution chain, permission management endpoints,
role boundary enforcement, and edge cases.
"""
from tests._app import db, db_session
from tests.conftest import login_superadmin, login_admin


def _headers(token):
    return {"Authorization": f"Bearer {token}"}


class TestCasbinPermissions:
    """Unit-level tests for the Casbin permission service."""

    def test_superadmin_gets_all_permissions(self):
        from api.Core.Permissions import (
            RBAC_ACTIONS, RBAC_RESOURCES, permissions_for,
        )
        perms = permissions_for("superadmin")
        for r in RBAC_RESOURCES:
            for a in RBAC_ACTIONS:
                assert f"{r}.{a}" in perms

    def test_superadmin_check_always_true(self):
        from api.Core.Permissions import check_permission
        assert check_permission("superadmin", None, "anything", "read") is True
        assert check_permission("superadmin", 999, "fake", "delete") is True

    def test_defaults_returned_when_no_casbin_rules(self):
        from api.Core.Permissions import (
            RBAC_DEFAULTS, permissions_for, _get_enforcer, seed_defaults,
        )
        e = _get_enforcer()
        e.clear_policy()
        e.save_policy()
        e.load_policy()
        perms = permissions_for("admin", store_id=1)
        expected = RBAC_DEFAULTS.get("admin", [])
        for p in expected:
            assert p in perms, f"Expected {p} in permissions"
        seed_defaults()

    def test_global_rules_override_defaults(self):
        from api.Core.Permissions import (
            set_global_permissions, permissions_for, seed_defaults,
            _get_enforcer,
        )
        set_global_permissions("admin", {
            "reports": {"read": True, "create": False, "update": False, "delete": False},
        })
        perms = permissions_for("admin", store_id=1)
        assert "reports.read" in perms
        assert "transfers.read" not in perms
        e = _get_enforcer()
        e.remove_filtered_policy(0, "admin", "global")
        e.save_policy()
        seed_defaults()

    def test_store_override_takes_priority(self):
        from api.Core.Permissions import (
            set_store_permissions, permissions_for, reset_store_to_defaults,
        )
        set_store_permissions(997, "admin", {
            "reports": {"read": True, "create": False, "update": False, "delete": False},
        })
        perms = permissions_for("admin", store_id=997)
        assert "reports.read" in perms
        assert "transfers.read" not in perms
        reset_store_to_defaults(997, "admin")

    def test_check_permission_live(self):
        from api.Core.Permissions import (
            check_permission, set_store_permissions, reset_store_to_defaults,
        )
        assert check_permission("admin", 996, "transfers", "read") is True
        set_store_permissions(996, "admin", {
            "reports": {"read": True, "create": False, "update": False, "delete": False},
        })
        assert check_permission("admin", 996, "transfers", "read") is False
        assert check_permission("admin", 996, "reports", "read") is True
        reset_store_to_defaults(996, "admin")

    def test_reset_falls_back_to_global(self):
        from api.Core.Permissions import (
            set_store_permissions, reset_store_to_defaults,
            check_permission,
        )
        set_store_permissions(995, "employee", {
            "transfers": {"read": False, "create": False, "update": False, "delete": False},
        })
        assert check_permission("employee", 995, "transfers", "read") is False
        reset_store_to_defaults(995, "employee")
        assert check_permission("employee", 995, "transfers", "read") is True

    def test_cross_store_isolation(self):
        from api.Core.Permissions import (
            set_store_permissions, check_permission, reset_store_to_defaults,
        )
        set_store_permissions(994, "employee", {
            "transfers": {"read": False, "create": False, "update": False, "delete": False},
        })
        assert check_permission("employee", 994, "transfers", "read") is False
        assert check_permission("employee", 993, "transfers", "read") is True
        reset_store_to_defaults(994, "employee")

    def test_owner_role_permissions(self):
        from api.Core.Permissions import permissions_for
        perms = permissions_for("owner", store_id=1)
        assert "transfers.read" in perms
        assert "settings.update" in perms
        assert "transfers.create" not in perms

    def test_employee_role_default_permissions(self):
        from api.Core.Permissions import permissions_for
        perms = permissions_for("employee", store_id=1)
        assert "transfers.create" in perms
        assert "transfers.read" in perms
        assert "reports.read" not in perms
        assert "settings.update" not in perms

    def test_permission_matrix_builder(self):
        from api.Core.Permissions import get_permission_matrix
        result = get_permission_matrix(1)
        assert "matrix" in result
        assert "admin" in result["matrix"]
        assert "employee" in result["matrix"]
        assert result["matrix"]["admin"]["transfers"]["read"] is True

    def test_global_matrix_builder(self):
        from api.Core.Permissions import get_global_matrix
        result = get_global_matrix()
        assert "admin" in result["matrix"]
        assert "employee" in result["matrix"]
        assert "owner" in result["matrix"]

    def test_all_permissions_off_persists(self):
        """Setting ALL permissions off should result in zero access,
        not silently fall back to global defaults (sentinel marker)."""
        from api.Core.Permissions import (
            set_store_permissions, check_permission, reset_store_to_defaults,
            RBAC_RESOURCES, RBAC_ACTIONS,
        )
        empty_matrix = {
            r: {a: False for a in RBAC_ACTIONS} for r in RBAC_RESOURCES
        }
        set_store_permissions(992, "employee", empty_matrix)
        for r in RBAC_RESOURCES:
            for a in RBAC_ACTIONS:
                assert check_permission("employee", 992, r, a) is False, \
                    f"employee.{r}.{a} should be False"
        reset_store_to_defaults(992, "employee")

    def test_invalid_resource_ignored_in_write(self):
        from api.Core.Permissions import (
            set_store_permissions, check_permission, reset_store_to_defaults,
        )
        set_store_permissions(991, "employee", {
            "fake_resource": {"read": True, "create": True, "update": True, "delete": True},
            "transfers": {"read": True, "create": False, "update": False, "delete": False},
        })
        assert check_permission("employee", 991, "transfers", "read") is True
        assert check_permission("employee", 991, "fake_resource", "read") is False
        reset_store_to_defaults(991, "employee")

    def test_invalid_action_ignored_in_write(self):
        from api.Core.Permissions import (
            set_store_permissions, check_permission, reset_store_to_defaults,
        )
        set_store_permissions(990, "employee", {
            "transfers": {"read": True, "fake_action": True, "create": False, "update": False, "delete": False},
        })
        assert check_permission("employee", 990, "transfers", "read") is True
        assert check_permission("employee", 990, "transfers", "fake_action") is False
        reset_store_to_defaults(990, "employee")

    def test_permission_check_with_none_store_id(self):
        """Roles with no store scope (owners) use RBAC_DEFAULTS."""
        from api.Core.Permissions import check_permission
        assert check_permission("owner", None, "transfers", "read") is True
        assert check_permission("admin", None, "transfers", "create") is True
        assert check_permission("employee", None, "settings", "delete") is False

    def test_reset_when_no_overrides_exist_is_noop(self):
        """Reset on a store with no overrides should not crash."""
        from api.Core.Permissions import (
            reset_store_to_defaults, check_permission,
        )
        reset_store_to_defaults(989, "employee")
        assert check_permission("employee", 989, "transfers", "read") is True

    def test_set_then_overwrite(self):
        """Saving a matrix twice should replace, not accumulate."""
        from api.Core.Permissions import (
            set_store_permissions, check_permission, reset_store_to_defaults,
        )
        set_store_permissions(988, "employee", {
            "reports": {"read": True, "create": True, "update": True, "delete": True},
        })
        assert check_permission("employee", 988, "reports", "create") is True
        set_store_permissions(988, "employee", {
            "reports": {"read": True, "create": False, "update": False, "delete": False},
        })
        assert check_permission("employee", 988, "reports", "create") is False
        assert check_permission("employee", 988, "reports", "read") is True
        reset_store_to_defaults(988, "employee")

    def test_global_change_does_not_affect_overridden_store(self):
        """A store with overrides should not be affected by global default changes."""
        from api.Core.Permissions import (
            set_store_permissions, set_global_permissions, check_permission,
            reset_store_to_defaults, _get_enforcer, seed_defaults,
        )
        set_store_permissions(987, "employee", {
            "reports": {"read": True, "create": False, "update": False, "delete": False},
        })
        set_global_permissions("employee", {
            "transfers": {"read": True, "create": True, "update": True, "delete": True},
        })
        # Store 987 still has only reports.read; global changes don't leak in
        assert check_permission("employee", 987, "reports", "read") is True
        assert check_permission("employee", 987, "transfers", "read") is False
        # Cleanup
        reset_store_to_defaults(987, "employee")
        e = _get_enforcer()
        e.remove_filtered_policy(0, "employee", "global")
        e.save_policy()
        seed_defaults()


class TestGlobalPermissionUpdate:
    """Integration tests for the superadmin global permissions endpoint."""

    def test_update_and_read_back(self, client, test_store_id):
        token = login_superadmin(client)
        resp = client.put(
            "/api/v2/superadmin/permissions",
            json={"changes": [
                {"role": "admin", "resource": "transfers", "action": "read", "allowed": False},
            ]},
            headers=_headers(token),
        )
        assert resp.status_code == 200
        matrix = resp.get_json()["matrix"]
        assert matrix["admin"]["transfers"]["read"] is False
        resp2 = client.put(
            "/api/v2/superadmin/permissions",
            json={"changes": [
                {"role": "admin", "resource": "transfers", "action": "read", "allowed": True},
            ]},
            headers=_headers(token),
        )
        assert resp2.get_json()["matrix"]["admin"]["transfers"]["read"] is True


class TestPerStorePermissions:
    """Integration tests for per-store permission overrides."""

    def test_admin_can_read_permissions(self, client, test_store_id):
        token = login_admin(client, test_store_id)
        resp = client.get(
            "/api/v2/admin/store-permissions",
            headers=_headers(token),
        )
        assert resp.status_code == 200
        assert "matrix" in resp.get_json()

    def test_admin_cannot_edit_admin_role(self, client, test_store_id):
        token = login_admin(client, test_store_id)
        resp = client.put(
            "/api/v2/admin/store-permissions",
            json={"matrix": {
                "admin": {"transfers": {"read": False, "create": False, "update": False, "delete": False}},
            }},
            headers=_headers(token),
        )
        assert resp.status_code == 403

    def test_admin_can_edit_employee_via_matrix(self, client, test_store_id):
        token = login_admin(client, test_store_id)
        resp_get = client.get("/api/v2/admin/store-permissions", headers=_headers(token))
        current = resp_get.get_json()["matrix"]["employee"]
        current["transfers"]["create"] = False
        resp = client.put(
            "/api/v2/admin/store-permissions",
            json={"matrix": {"employee": current}},
            headers=_headers(token),
        )
        assert resp.status_code == 200
        assert resp.get_json()["matrix"]["employee"]["transfers"]["create"] is False
        assert resp.get_json()["matrix"]["employee"]["transfers"]["read"] is True

    def test_partial_removal_persists(self, client, test_store_id):
        token = login_admin(client, test_store_id)
        resp_get = client.get("/api/v2/admin/store-permissions", headers=_headers(token))
        current = resp_get.get_json()["matrix"]["employee"]
        current["transfers"]["create"] = False
        current["transfers"]["update"] = False
        resp = client.put(
            "/api/v2/admin/store-permissions",
            json={"matrix": {"employee": current}},
            headers=_headers(token),
        )
        assert resp.status_code == 200
        m = resp.get_json()["matrix"]
        assert m["employee"]["transfers"]["read"] is True
        assert m["employee"]["transfers"]["create"] is False
        assert m["employee"]["transfers"]["update"] is False

    def test_save_idempotent(self, client, test_store_id):
        token = login_admin(client, test_store_id)
        resp_get = client.get("/api/v2/admin/store-permissions", headers=_headers(token))
        current = resp_get.get_json()["matrix"]["employee"]
        current["transfers"]["create"] = False
        resp1 = client.put(
            "/api/v2/admin/store-permissions",
            json={"matrix": {"employee": current}},
            headers=_headers(token),
        )
        resp2 = client.put(
            "/api/v2/admin/store-permissions",
            json={"matrix": {"employee": current}},
            headers=_headers(token),
        )
        assert resp1.get_json()["matrix"] == resp2.get_json()["matrix"]

    def test_reset_then_edit(self, client, test_store_id):
        token = login_admin(client, test_store_id)
        resp_get = client.get("/api/v2/admin/store-permissions", headers=_headers(token))
        current = resp_get.get_json()["matrix"]["employee"]
        current["reports"]["read"] = False
        client.put(
            "/api/v2/admin/store-permissions",
            json={"matrix": {"employee": current}},
            headers=_headers(token),
        )
        client.post(
            "/api/v2/admin/store-permissions/reset",
            json={"role": "employee"},
            headers=_headers(token),
        )
        resp_get2 = client.get("/api/v2/admin/store-permissions", headers=_headers(token))
        current2 = resp_get2.get_json()["matrix"]["employee"]
        current2["transfers"]["create"] = False
        resp = client.put(
            "/api/v2/admin/store-permissions",
            json={"matrix": {"employee": current2}},
            headers=_headers(token),
        )
        assert resp.status_code == 200
        m = resp.get_json()["matrix"]
        assert m["employee"]["transfers"]["read"] is True
        assert m["employee"]["transfers"]["create"] is False

    def test_invalid_role_rejected(self, client, test_store_id):
        token = login_admin(client, test_store_id)
        resp = client.put(
            "/api/v2/admin/store-permissions",
            json={"matrix": {"superadmin": {"transfers": {"read": False}}}},
            headers=_headers(token),
        )
        assert resp.status_code == 403

    def test_empty_changes_noop(self, client, test_store_id):
        token = login_admin(client, test_store_id)
        resp = client.put(
            "/api/v2/admin/store-permissions",
            json={"changes": []},
            headers=_headers(token),
        )
        assert resp.status_code == 200


class TestSuperadminPerStorePermissions:

    def test_superadmin_per_store_edit(self, client, test_store_id):
        token = login_superadmin(client)
        resp_get = client.get(
            f"/api/v2/superadmin/stores/{test_store_id}/permissions",
            headers=_headers(token),
        )
        current = resp_get.get_json()["matrix"]["admin"]
        current["transfers"]["create"] = False
        current["transfers"]["update"] = False
        current["transfers"]["delete"] = False
        resp = client.put(
            f"/api/v2/superadmin/stores/{test_store_id}/permissions",
            json={"matrix": {"admin": current}},
            headers=_headers(token),
        )
        assert resp.status_code == 200
        m = resp.get_json()["matrix"]
        assert m["admin"]["transfers"]["read"] is True
        assert m["admin"]["transfers"]["create"] is False

    def test_live_enforcement(self, client, test_store_id):
        """Permission change via superadmin blocks admin immediately."""
        sa_token = login_superadmin(client)
        resp_get = client.get(
            f"/api/v2/superadmin/stores/{test_store_id}/permissions",
            headers=_headers(sa_token),
        )
        current = resp_get.get_json()["matrix"]["admin"]
        for a in ["create", "read", "update", "delete"]:
            current["transfers"][a] = False
        client.put(
            f"/api/v2/superadmin/stores/{test_store_id}/permissions",
            json={"matrix": {"admin": current}},
            headers=_headers(sa_token),
        )
        admin_token = login_admin(client, test_store_id)
        resp = client.get(
            f"/api/v2/transfers?store_ids={test_store_id}",
            headers=_headers(admin_token),
        )
        assert resp.status_code == 403
