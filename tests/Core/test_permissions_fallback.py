"""Tests for the Casbin-failure fallback in api.Core.Permissions.

The risk this guards against: if Casbin throws (DB connection issue,
adapter bug, missing table), login must not 500. The fallback path
returns RBAC_DEFAULTS so the user can still get in.
"""
from unittest.mock import patch


def test_permissions_for_falls_back_when_casbin_throws():
    """If _resolve_grants raises, permissions_for returns
    legacy + RBAC_DEFAULTS for the role instead of propagating."""
    from api.Core.Permissions import (
        permissions_for, RBAC_DEFAULTS, LEGACY_ROLE_PERMISSIONS,
    )
    with patch(
        "api.Core.Permissions._resolve_grants",
        side_effect=RuntimeError("simulated Casbin failure"),
    ):
        perms = permissions_for("admin", store_id=1)
    expected = (
        list(LEGACY_ROLE_PERMISSIONS["admin"])
        + list(RBAC_DEFAULTS["admin"])
    )
    assert perms == expected


def test_permissions_for_falls_back_employee_role():
    from api.Core.Permissions import (
        permissions_for, RBAC_DEFAULTS, LEGACY_ROLE_PERMISSIONS,
    )
    with patch(
        "api.Core.Permissions._resolve_grants",
        side_effect=Exception("boom"),
    ):
        perms = permissions_for("employee", store_id=1)
    for p in RBAC_DEFAULTS["employee"]:
        assert p in perms
    for legacy in LEGACY_ROLE_PERMISSIONS["employee"]:
        assert legacy in perms


def test_check_permission_falls_back_to_defaults():
    """If _resolve_grants throws, check_permission consults
    RBAC_DEFAULTS instead of crashing the request."""
    from api.Core.Permissions import check_permission
    with patch(
        "api.Core.Permissions._resolve_grants",
        side_effect=ConnectionError("db unreachable"),
    ):
        # transfers.read IS in admin defaults
        assert check_permission("admin", 1, "transfers", "read") is True
        # nonexistent action is NOT in defaults → False
        assert check_permission("admin", 1, "fake", "delete") is False


def test_check_permission_fallback_respects_employee_scope():
    """Employee defaults: transfers.create/read/update yes,
    transfers.delete no. Fallback must preserve this."""
    from api.Core.Permissions import check_permission
    with patch(
        "api.Core.Permissions._resolve_grants",
        side_effect=Exception("Casbin down"),
    ):
        assert check_permission("employee", 1, "transfers", "read") is True
        assert check_permission("employee", 1, "transfers", "create") is True
        assert check_permission("employee", 1, "transfers", "delete") is False
        assert check_permission("employee", 1, "settings", "update") is False


def test_superadmin_bypass_skips_resolve_grants():
    """Superadmin must never hit Casbin — return all permissions
    directly, so a Casbin outage doesn't lock out the platform admin."""
    from api.Core.Permissions import permissions_for, check_permission
    with patch(
        "api.Core.Permissions._resolve_grants",
        side_effect=RuntimeError("should not be called"),
    ) as mock:
        perms = permissions_for("superadmin")
        assert "transfers.read" in perms
        assert check_permission("superadmin", 1, "anything", "delete") is True
        mock.assert_not_called()
