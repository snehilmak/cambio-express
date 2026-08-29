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
    "day_close", "catalog",
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
        # Cashiers submit their own register/shift close.
        "day_close.create", "day_close.read",
        # Cashiers look items up in the price book; managing the
        # catalog (items + vendors) stays admin-side.
        "catalog.read",
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

def _global_grants(role: str) -> set[tuple[str, str]]:
    """Global (resource, action) grants for a role — Casbin global
    domain, falling back to RBAC_DEFAULTS when unseeded."""
    e = _get_enforcer()
    global_rules = e.get_filtered_policy(0, role, "global")
    if global_rules:
        return {(r[2], r[3]) for r in global_rules}
    defaults = RBAC_DEFAULTS.get(role, [])
    return {tuple(p.split(".", 1)) for p in defaults if "." in p}


def _store_overlay(
    store_rules: list[list[str]],
) -> tuple[set[str], set[tuple[str, str]], bool]:
    """Split a store domain's rows into (mentioned resources,
    grants, legacy_all_off). ``__none__`` action rows mention a
    resource with zero grants; the legacy ``__override_active__``
    sentinel marks an old-format all-off save."""
    mentioned: set[str] = set()
    grants: set[tuple[str, str]] = set()
    legacy_all_off = False
    for r in store_rules:
        resource, action = r[2], r[3]
        if resource == _OVERRIDE_SENTINEL:
            legacy_all_off = True
            continue
        mentioned.add(resource)
        if action != _RESOURCE_NONE:
            grants.add((resource, action))
    return mentioned, grants, legacy_all_off


def _resolve_grants(role: str, store_id: int) -> set[tuple[str, str]]:
    """Effective (resource, action) grants for a role at a store.

    Store overrides are a PER-RESOURCE overlay, not a wholesale
    replacement: rows govern only the resources they mention (a
    ``__none__`` marker mentions a resource with all actions off);
    resources the override never mentions fall back to the global
    defaults. This is what lets a NEW platform resource (lottery,
    day_close, catalog…) reach stores whose override matrix was
    saved before the resource existed — the old wholesale
    semantics froze those stores out of every later resource.

    Legacy compatibility: a pre-overlay all-off save is a lone
    ``__override_active__`` sentinel → still means zero access.
    A pre-overlay partial save has no markers, so its switched-off
    resources fall back to global once; the next save re-freezes
    them explicitly.
    """
    e = _get_enforcer()
    store_rules = e.get_filtered_policy(0, role, str(store_id))
    if not store_rules:
        return _global_grants(role)
    mentioned, grants, legacy_all_off = _store_overlay(store_rules)
    if legacy_all_off and not mentioned:
        return set()
    return grants | {
        (resource, action)
        for resource, action in _global_grants(role)
        if resource not in mentioned
    }


# ── Per-user overlay (R-1) ─────────────────────────────────
#
# A third layer ABOVE the role layers: rows whose subject is
# ``user:<id>`` in the store's domain. Same per-resource overlay
# semantics as the store layer — user rows govern only the
# resources they mention (a ``__none__`` marker mentions a
# resource with zero grants); unmentioned resources fall back to
# the role's resolved grants. This is what makes "Amber gets
# time clock + transfers but can't see any numbers" expressible
# without forking the role system, and it is a SECURITY boundary
# (unlike ``User.module_access``, which is nav-only UX gating).


def _user_subject(user_id: int) -> str:
    return f"user:{int(user_id)}"


def _user_overlay(
    user_id: int, store_id: int,
) -> tuple[set[str], set[tuple[str, str]]]:
    """(mentioned resources, grants) from the user's own rows."""
    e = _get_enforcer()
    rules = e.get_filtered_policy(
        0, _user_subject(user_id), str(store_id),
    )
    mentioned: set[str] = set()
    grants: set[tuple[str, str]] = set()
    for r in rules:
        resource, action = r[2], r[3]
        mentioned.add(resource)
        if action != _RESOURCE_NONE:
            grants.add((resource, action))
    return mentioned, grants


def resolve_user_grants(
    user_id: int, role: str, store_id: int,
) -> set[tuple[str, str]]:
    """Effective grants for one USER at a store: the user's own
    overlay where it speaks, the role's resolved grants where it
    doesn't."""
    mentioned, grants = _user_overlay(user_id, store_id)
    role_grants = _resolve_grants(role, store_id)
    if not mentioned:
        return role_grants
    return grants | {
        (resource, action)
        for resource, action in role_grants
        if resource not in mentioned
    }


def user_has_custom_permissions(user_id: int, store_id: int) -> bool:
    """True when the user carries any overlay rows at this store."""
    try:
        e = _get_enforcer()
        return bool(e.get_filtered_policy(
            0, _user_subject(user_id), str(store_id),
        ))
    except Exception:
        return False


# ── Public read API ────────────────────────────────────────

def check_permission(
    role: str, store_id: int | None,
    resource: str, action: str,
    user_id: int | None = None,
) -> bool:
    """Live permission check. Superadmin always passes.

    ``user_id`` (when provided with a store scope) applies the
    per-user overlay above the role layers — callers that omit it
    get pure role resolution, so pre-R-1 call sites keep their
    exact behavior.

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
        if user_id is not None:
            return (resource, action) in resolve_user_grants(
                int(user_id), role, store_id,
            )
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
    role: str, store_id: int | None = None,
    user_id: int | None = None, **_kw: Any,
) -> list[str]:
    """Full permission list for a principal. Used for JWT claims.
    Accepts **kwargs for backward compat (old callers pass db=).

    ``user_id`` (with a store scope) bakes the per-user overlay
    into the list, so a restricted user's token never carries
    perms their overlay denies. Role-only callers are unchanged.

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
        if user_id is not None:
            grants = resolve_user_grants(int(user_id), role, store_id)
        else:
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

# Legacy all-off marker (read-compat only — no longer written).
_OVERRIDE_SENTINEL = "__override_active__"
# Per-resource "mentioned with zero grants" marker. Every save
# writes one for each current resource with no allowed action, so
# the overlay knows "explicitly off" from "didn't exist yet".
_RESOURCE_NONE = "__none__"


def set_store_permissions(
    store_id: int, role: str,
    matrix: dict[str, dict[str, bool]],
) -> None:
    """Replace the per-store overlay for a role. Every CURRENT
    resource is written explicitly — grants, or a ``__none__``
    marker when all its actions are off — so resources added to
    the platform later fall back to global defaults until the
    matrix is saved again (see ``_resolve_grants``)."""
    e = _get_enforcer()
    dom = str(store_id)
    e.remove_filtered_policy(0, role, dom)
    for resource in RBAC_RESOURCES:
        actions = matrix.get(resource, {})
        any_allowed = False
        for action in RBAC_ACTIONS:
            if actions.get(action):
                e.add_policy(role, dom, resource, action)
                any_allowed = True
        if not any_allowed:
            e.add_policy(role, dom, resource, _RESOURCE_NONE)
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


def set_user_permissions(
    store_id: int, user_id: int,
    matrix: dict[str, dict[str, bool]],
) -> None:
    """Replace the per-USER overlay at a store. Same explicit-write
    contract as ``set_store_permissions``: every CURRENT resource
    gets grants or a ``__none__`` marker, so resources added to the
    platform later fall back to the user's role until the matrix is
    saved again. This is a SECURITY write — callers must audit it
    and revoke the user's live sessions so old JWT perms die."""
    e = _get_enforcer()
    sub, dom = _user_subject(user_id), str(store_id)
    e.remove_filtered_policy(0, sub, dom)
    for resource in RBAC_RESOURCES:
        actions = matrix.get(resource, {})
        any_allowed = False
        for action in RBAC_ACTIONS:
            if actions.get(action):
                e.add_policy(sub, dom, resource, action)
                any_allowed = True
        if not any_allowed:
            e.add_policy(sub, dom, resource, _RESOURCE_NONE)
    e.save_policy()
    reload_policy()


def clear_user_permissions(store_id: int, user_id: int) -> None:
    """Remove the per-user overlay — the user goes back to pure
    role resolution. Also a session-revoking security write."""
    e = _get_enforcer()
    e.remove_filtered_policy(0, _user_subject(user_id), str(store_id))
    e.save_policy()
    reload_policy()


def get_user_permission_matrix(
    user_id: int, role: str, store_id: int,
) -> dict:
    """Resolved effective matrix for one user (overlay applied over
    the role layers) plus whether an overlay exists — feeds the
    per-user access editor in the admin user form."""
    granted = resolve_user_grants(user_id, role, store_id)
    matrix: dict[str, dict[str, bool]] = {}
    for resource in RBAC_RESOURCES:
        matrix[resource] = {
            action: (resource, action) in granted
            for action in RBAC_ACTIONS
        }
    return {
        "user_id": user_id,
        "role": role,
        "store_id": store_id,
        "resources": RBAC_RESOURCES,
        "actions": RBAC_ACTIONS,
        "matrix": matrix,
        "has_custom": user_has_custom_permissions(user_id, store_id),
    }


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
            # Same per-resource overlay as _resolve_grants, so the
            # UI shows the grants that are actually enforced.
            granted = _resolve_grants(role, store_id)
        else:
            granted = _global_grants(role)

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
