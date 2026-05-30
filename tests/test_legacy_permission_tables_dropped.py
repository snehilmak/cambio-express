"""Verifies the legacy permission tables (role_permission and
store_role_override) are dropped post-Casbin migration.

If these tables come back, it means someone reintroduced the old
models or a downgrade migration was applied — both warrant
investigation since Casbin is now the source of truth.
"""
from sqlalchemy import inspect

from api.Core.Database.session import _get_engine


def _table_names() -> set[str]:
    return set(inspect(_get_engine()).get_table_names())


def test_role_permission_table_does_not_exist():
    assert "role_permission" not in _table_names(), (
        "role_permission table should have been dropped — Casbin is "
        "now the source of truth for RBAC policies"
    )


def test_store_role_override_table_does_not_exist():
    assert "store_role_override" not in _table_names(), (
        "store_role_override table should have been dropped — Casbin "
        "handles per-store overrides via casbin_rule.v1 = store_id"
    )


def test_casbin_rule_table_exists():
    assert "casbin_rule" in _table_names(), (
        "casbin_rule table must exist — Casbin policies are stored there"
    )


def test_legacy_models_not_importable():
    """The RolePermission and StoreRoleOverride model classes
    should no longer exist."""
    from api.Modules.Auth import Models as auth_models
    assert not hasattr(auth_models, "RolePermission"), (
        "RolePermission model should be removed from api.Modules.Auth.Models"
    )
    assert not hasattr(auth_models, "StoreRoleOverride"), (
        "StoreRoleOverride model should be removed"
    )
