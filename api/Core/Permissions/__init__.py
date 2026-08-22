"""Casbin-backed RBAC permission service.

Replaces the custom three-tier resolution (StoreRoleOverride →
RolePermission → RBAC_DEFAULTS) with a Casbin enforcer backed by
SQLAlchemy.

Policy rows live in the ``casbin_rule`` table (auto-created by the
adapter). Each row is (ptype, v0=role, v1=domain, v2=resource,
v3=action). Domain is ``"global"`` for defaults or ``str(store_id)``
for per-store overrides.

Resolution:
  1. Per-store rules (domain = store_id) → use exclusively
  2. Global rules (domain = "global") → fallback
  3. RBAC_DEFAULTS (hardcoded) → boot-time only, before first seed

Superadmin bypasses all checks.
"""
from __future__ import annotations

import logging
import os
from typing import Any

import casbin
from casbin_sqlalchemy_adapter import Adapter as CasbinAdapter
from fastapi import HTTPException

_log = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────

RBAC_RESOURCES = [
    "transfers", "customers", "daily_book", "monthly",
    "batches", "bank_sync", "reports", "settings",
    "users", "time_clock", "return_checks", "lottery",
]
RBAC_ACTIONS = ["create", "read", "update", "delete"]

RBAC_DEFAULTS: dict[str, list[str]] = {
    "admin": [f"{r}.{a}" for r in RBAC_RESOURCES for a in RBAC_ACTIONS],
    "employee": [
        "transfers.create", "transfers.read", "transfers.update",
        "customers.create", "customers.read", "customers.update",
        "daily_book.read",
        "time_clock.create", "time_clock.read",
        "return_checks.read",
        # Cashiers enter the lottery day-close counts.
        "lottery.create", "lottery.read",
    ],
    "owner": (
        [f"{r}.read" for r in RBAC_RESOURCES]
        + ["settings.create", "settings.update", "settings.delete",
           "users.create"]
    ),
}

LEGACY_ROLE_PERMISSIONS: dict[str, list[str]] = {
    "superadmin": ["platform.admin", "store.admin", "store.employee", "owner.read"],
    # Tickets-only platform role. Deliberately NOT in the
    # superadmin bypasses in check_permission / require_permission /
    # permissions_for — support's whole surface is the Support
    # module, gated by PLATFORM_STAFF_ROLES there.
    "support": ["platform.support"],
    "owner": ["owner.read", "owner.admin"],
    "admin": ["store.admin", "store.employee"],
    "employee": ["store.employee"],
}


# ── Enforcer singleton ─────────────────────────────────────

_enforcer: casbin.Enforcer | None = None


def _model_path() -> str:
    return os.path.join(os.path.dirname(__file__), "model.conf")


def _get_enforcer() -> casbin.Enforcer:
    """Lazy-init the module-level enforcer singleton. If the prior
    init failed (or the singleton was reset), try again — letting a
    transient DB hiccup poison the process forever was an outage
    waiting to happen."""
    global _enforcer
    if _enforcer is not None:
        return _enforcer
    from api.Core.Database.session import _get_engine
    engine = _get_engine()
    adapter = CasbinAdapter(engine)
    _enforcer = casbin.Enforcer(_model_path(), adapter)
    return _enforcer


def _reset_enforcer() -> None:
    """Drop the singleton so the next call rebuilds it. Used by tests."""
    global _enforcer
    _enforcer = None


def reload_policy() -> None:
    """Re-read all rules from the DB into the in-memory enforcer."""
    _get_enforcer().load_policy()


# ── Internal helpers ───────────────────────────────────────

def _resolve_grants(role: str, store_id: int) -> set[tuple[str, str]]:
    """Effective (resource, action) grants for a role at a store."""
    e = _get_enforcer()
    dom = str(store_id)
    store_rules = e.get_filtered_policy(0, role, dom)
    if store_rules:
        return {
            (r[2], r[3]) for r in store_rules
            if r[2] != _OVERRIDE_SENTINEL
        }
    global_rules = e.get_filtered_policy(0, role, "global")
    if global_rules:
        return {(r[2], r[3]) for r in global_rules}
    defaults = RBAC_DEFAULTS.get(role, [])
    return {tuple(p.split(".", 1)) for p in defaults if "." in p}


# ── Public read API ────────────────────────────────────────

def check_permission(
    role: str, store_id: int | None,
    resource: str, action: str,
) -> bool:
    """Live permission check. Superadmin always passes.

    If Casbin throws, we fall back to ``RBAC_DEFAULTS`` so a
    permission-system fault doesn't lock everyone out. The
    Auth/Services/principal layer additionally checks the JWT
    perms claim, so the user's view doesn't get more open than
    what was baked into their token at login time."""
    if role == "superadmin":
        return True
    if store_id is None:
        return f"{resource}.{action}" in RBAC_DEFAULTS.get(role, [])
    try:
        return (resource, action) in _resolve_grants(role, store_id)
    except Exception as exc:
        _log.warning(
            "check_permission: Casbin lookup failed for role=%s "
            "store_id=%s resource=%s action=%s — falling back to "
            "RBAC_DEFAULTS. Error: %s",
            role, store_id, resource, action, exc,
        )
        return f"{resource}.{action}" in RBAC_DEFAULTS.get(role, [])


def require_permission(
    claims: dict[str, Any], resource: str, action: str,
) -> None:
    """Raise 403 if the principal lacks permission."""
    role = claims.get("role", "")
    if role == "superadmin":
        return
    store_id = claims.get("store_id")
    if not check_permission(role, store_id, resource, action):
        raise HTTPException(
            status_code=403,
            detail=f"Missing permission: {resource}.{action}",
        )


def permissions_for(
    role: str, store_id: int | None = None, **_kw: Any,
) -> list[str]:
    """Full permission list for a role. Used for JWT claims.
    Accepts **kwargs for backward compat (old callers pass db=).

    If Casbin throws (DB connection issue, missing table, etc.)
    we fall back to ``RBAC_DEFAULTS`` so login never 500s on a
    permissions-system fault. The login path then issues a JWT
    with the hardcoded defaults; the user can still operate and
    ops can fix Casbin without an outage."""
    legacy = list(LEGACY_ROLE_PERMISSIONS.get(role, []))
    if role == "superadmin":
        return legacy + [f"{r}.{a}" for r in RBAC_RESOURCES for a in RBAC_ACTIONS]
    if store_id is None:
        return legacy + list(RBAC_DEFAULTS.get(role, []))
    try:
        grants = _resolve_grants(role, store_id)
        return legacy + [f"{r}.{a}" for r, a in grants]
    except Exception as exc:
        _log.warning(
            "permissions_for: Casbin lookup failed for role=%s "
            "store_id=%s — falling back to RBAC_DEFAULTS. Error: %s",
            role, store_id, exc,
        )
        return legacy + list(RBAC_DEFAULTS.get(role, []))


# ── Write API ──────────────────────────────────────────────

_OVERRIDE_SENTINEL = "__override_active__"


def set_store_permissions(
    store_id: int, role: str,
    matrix: dict[str, dict[str, bool]],
) -> None:
    """Replace all per-store permissions for a role.
    A sentinel row marks that overrides exist even if all are off."""
    e = _get_enforcer()
    dom = str(store_id)
    e.remove_filtered_policy(0, role, dom)
    has_any = False
    for resource, actions in matrix.items():
        if resource not in RBAC_RESOURCES:
            continue
        for action, allowed in actions.items():
            if action not in RBAC_ACTIONS:
                continue
            if allowed:
                e.add_policy(role, dom, resource, action)
                has_any = True
    if not has_any:
        e.add_policy(role, dom, _OVERRIDE_SENTINEL, _OVERRIDE_SENTINEL)
    e.save_policy()
    reload_policy()


def set_global_permissions(
    role: str,
    matrix: dict[str, dict[str, bool]],
) -> None:
    """Replace global defaults for a role."""
    e = _get_enforcer()
    e.remove_filtered_policy(0, role, "global")
    for resource, actions in matrix.items():
        if resource not in RBAC_RESOURCES:
            continue
        for action, allowed in actions.items():
            if action not in RBAC_ACTIONS:
                continue
            if allowed:
                e.add_policy(role, "global", resource, action)
    e.save_policy()
    reload_policy()


def reset_store_to_defaults(store_id: int, role: str) -> None:
    """Remove per-store overrides for a role."""
    e = _get_enforcer()
    e.remove_filtered_policy(0, role, str(store_id))
    e.save_policy()
    reload_policy()


def seed_defaults() -> None:
    """Seed global defaults if Casbin is empty. Idempotent."""
    e = _get_enforcer()
    if e.get_policy():
        return
    for role, perms in RBAC_DEFAULTS.items():
        for perm in perms:
            resource, action = perm.split(".", 1)
            e.add_policy(role, "global", resource, action)
    e.save_policy()
    _log.info("Casbin: seeded %d default rules",
              sum(len(v) for v in RBAC_DEFAULTS.values()))


def ensure_resource_defaults(resource: str) -> None:
    """Additively seed the default rules for ONE resource into an
    ALREADY-SEEDED policy store — the path a brand-new resource
    (e.g. "lottery") takes on existing databases, where
    ``seed_defaults`` is a no-op because policy is non-empty.

    Additive only: rows that already exist are left alone and
    nothing is ever removed, so per-store overrides and superadmin
    edits survive. Idempotent — safe to call on every boot.
    """
    e = _get_enforcer()
    if not e.get_policy():
        return  # empty store → seed_defaults handles the full set
    added = 0
    for role, perms in RBAC_DEFAULTS.items():
        for perm in perms:
            r, action = perm.split(".", 1)
            if r != resource:
                continue
            if not e.has_policy(role, "global", r, action):
                e.add_policy(role, "global", r, action)
                added += 1
    if added:
        e.save_policy()
        _log.info(
            "Casbin: additively seeded %d default rules for new "
            "resource %r", added, resource,
        )


# ── Matrix builders (for permission UI endpoints) ──────────

def get_permission_matrix(
    store_id: int,
    visible_roles: list[str] | None = None,
    editable_roles: list[str] | None = None,
) -> dict:
    """Build the permission matrix for the store permissions UI."""
    if visible_roles is None:
        visible_roles = ["admin", "employee"]
    if editable_roles is None:
        editable_roles = visible_roles

    matrix: dict[str, dict[str, dict[str, bool]]] = {}
    has_overrides: list[str] = []
    e = _get_enforcer()

    for role in visible_roles:
        dom = str(store_id)
        store_rules = e.get_filtered_policy(0, role, dom)
        if store_rules:
            has_overrides.append(role)
            granted = {
                (r[2], r[3]) for r in store_rules
                if r[2] != _OVERRIDE_SENTINEL
            }
        else:
            global_rules = e.get_filtered_policy(0, role, "global")
            if global_rules:
                granted = {(r[2], r[3]) for r in global_rules}
            else:
                granted = {
                    tuple(p.split(".", 1))
                    for p in RBAC_DEFAULTS.get(role, []) if "." in p
                }

        matrix[role] = {}
        for resource in RBAC_RESOURCES:
            matrix[role][resource] = {}
            for action in RBAC_ACTIONS:
                matrix[role][resource][action] = (resource, action) in granted

    return {
        "store_id": store_id,
        "roles": visible_roles,
        "editable_roles": editable_roles,
        "resources": RBAC_RESOURCES,
        "actions": RBAC_ACTIONS,
        "matrix": matrix,
        "has_overrides": has_overrides,
    }


def get_global_matrix() -> dict:
    """Build the global permission matrix for superadmin UI."""
    e = _get_enforcer()
    granted: set[tuple[str, str, str]] = set()
    for r in e.get_policy():
        if r[1] == "global":
            granted.add((r[0], r[2], r[3]))
    if not granted:
        for role, perms in RBAC_DEFAULTS.items():
            for perm in perms:
                res, act = perm.split(".", 1)
                granted.add((role, res, act))

    roles = ["admin", "employee", "owner"]
    matrix: dict[str, dict[str, dict[str, bool]]] = {}
    for role in roles:
        matrix[role] = {}
        for resource in RBAC_RESOURCES:
            matrix[role][resource] = {}
            for action in RBAC_ACTIONS:
                matrix[role][resource][action] = (role, resource, action) in granted

    return {
        "roles": roles,
        "resources": RBAC_RESOURCES,
        "actions": RBAC_ACTIONS,
        "matrix": matrix,
    }
