"""Admin — named access roles (R-3).

"Save this matrix as a role", so two people meant to have the same
access actually get it, and keep it.

The whole feature rests on one decision: a role **owns its members'
overlays**. It adds no layer to permission resolution — assigning
or editing a role writes through ``set_user_permissions`` into the
per-user Casbin overlay R-1 already built, so ``check_permission``,
``resolve_user_grants`` and JWT baking are untouched. The
resolution order is a documented security contract (Auth
INVARIANTS.md); a convenience feature has no business rewriting it.

Three rules follow from that, and every caller depends on them:

1. **Propagation is LIVE.** Editing a role rewrites every member's
   overlay. Callers MUST audit the edit and revoke each member's
   sessions — it is the same security write as editing one user's
   access, multiplied.
2. **A role is the complete answer.** Only grants are stored; a
   resource the role does not mention is denied for its members,
   not inherited from their base role. Same explicit-write contract
   as a hand-ticked matrix.
3. **Editing one member individually detaches them.** They keep the
   matrix you just gave them and lose the role label. Leaving them
   attached would mean the next role edit silently reverts an edit
   someone watched succeed.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from api.Core.Clock import utc_now
from api.Core.Permissions import (
    RBAC_ACTIONS, RBAC_RESOURCES, set_user_permissions,
)
from api.Modules.Tenancy.Models import StoreRole, StoreRolePermission, User


class RoleError(Exception):
    """User-safe failure (duplicate name, unknown role…)."""


class RoleNotFoundError(RoleError):
    """No such role in this store."""


MAX_NAME = 60


def _clean_name(raw: str) -> str:
    name = (raw or "").strip()
    if not name:
        raise RoleError("Give the role a name.")
    return name[:MAX_NAME]


def get_role(db: Session, store_id: int, role_id: int) -> StoreRole:
    role = (
        db.query(StoreRole)
        .filter(StoreRole.id == role_id, StoreRole.store_id == store_id)
        .first()
    )
    if role is None:
        raise RoleNotFoundError("Role not found.")
    return role


def role_matrix(role: StoreRole) -> dict[str, dict[str, bool]]:
    """The role's full resource × action matrix.

    Built across EVERY current resource, not just the ones with
    stored rows, so a resource added to the platform later shows up
    as denied rather than missing — which is what the stored grants
    already mean.
    """
    granted = {(p.resource, p.action) for p in role.permissions}
    return {
        resource: {
            action: (resource, action) in granted
            for action in RBAC_ACTIONS
        }
        for resource in RBAC_RESOURCES
    }


def _write_matrix(
    db: Session, role: StoreRole, matrix: dict[str, dict[str, bool]],
) -> None:
    """Replace the role's stored grants. Unknown resources and
    actions are dropped rather than stored: a typo must not become
    a permission row that nothing can ever check."""
    role.permissions.clear()
    db.flush()
    for resource in RBAC_RESOURCES:
        actions = matrix.get(resource) or {}
        for action in RBAC_ACTIONS:
            if actions.get(action):
                role.permissions.append(StoreRolePermission(
                    store_id=role.store_id,
                    resource=resource, action=action,
                ))
    role.updated_at = utc_now()
    db.flush()


def members(db: Session, store_id: int, role_id: int) -> list[User]:
    """Everyone currently wearing this role, for the confirmation
    dialog that names them before a propagating edit."""
    return (
        db.query(User)
        .filter(User.store_id == store_id, User.store_role_id == role_id)
        .order_by(User.id.asc())
        .all()
    )


def member_counts(db: Session, store_id: int) -> dict[int, int]:
    """``{role_id: member count}`` for the roles list, in one query
    rather than one per row."""
    from sqlalchemy import func

    rows = (
        db.query(User.store_role_id, func.count(User.id))
        .filter(
            User.store_id == store_id,
            User.store_role_id.isnot(None),
        )
        .group_by(User.store_role_id)
        .all()
    )
    return {int(rid): int(count) for rid, count in rows}


def list_roles(db: Session, store_id: int) -> list[StoreRole]:
    return (
        db.query(StoreRole)
        .filter(StoreRole.store_id == store_id)
        .order_by(StoreRole.name.asc())
        .all()
    )


def create_role(
    db: Session, store_id: int, *, name: str,
    matrix: dict[str, dict[str, bool]], created_by: int | None,
) -> StoreRole:
    clean = _clean_name(name)
    existing = (
        db.query(StoreRole.id)
        .filter(StoreRole.store_id == store_id, StoreRole.name == clean)
        .first()
    )
    if existing:
        raise RoleError(f"A role named {clean!r} already exists.")
    role = StoreRole(
        store_id=store_id, name=clean, created_by=created_by,
        created_at=utc_now(), updated_at=utc_now(),
    )
    db.add(role)
    db.flush()
    _write_matrix(db, role, matrix)
    return role


def update_role(
    db: Session, store_id: int, role_id: int, *,
    name: str | None = None,
    matrix: dict[str, dict[str, bool]] | None = None,
) -> tuple[StoreRole, list[User]]:
    """Rename and/or re-matrix a role.

    Returns the role and the members whose overlays were rewritten
    — empty when only the name changed. **The caller must audit the
    change and revoke each returned member's sessions**; this
    function performs the security write but cannot see the acting
    principal.
    """
    role = get_role(db, store_id, role_id)
    if name is not None:
        clean = _clean_name(name)
        if clean != role.name:
            clash = (
                db.query(StoreRole.id)
                .filter(
                    StoreRole.store_id == store_id,
                    StoreRole.name == clean,
                    StoreRole.id != role.id,
                )
                .first()
            )
            if clash:
                raise RoleError(f"A role named {clean!r} already exists.")
            role.name = clean
            role.updated_at = utc_now()

    if matrix is None:
        db.flush()
        return role, []

    _write_matrix(db, role, matrix)
    affected = apply_to_members(db, store_id, role)
    return role, affected


def apply_to_members(
    db: Session, store_id: int, role: StoreRole,
) -> list[User]:
    """Push the role's matrix onto every member's overlay — the
    live propagation the whole feature is for."""
    resolved = role_matrix(role)
    affected = members(db, store_id, role.id)
    for user in affected:
        set_user_permissions(store_id, user.id, resolved)
    return affected


def assign_role(
    db: Session, store_id: int, user: User, role_id: int | None,
) -> StoreRole | None:
    """Put a user in a role (or take them out of one).

    Assigning writes the overlay immediately, so the user is
    already restricted at first login rather than at their second.

    Un-assigning (``role_id=None``) LEAVES the overlay in place:
    the user keeps exactly the access they had, it simply stops
    tracking the role. Silently widening someone's access because a
    label was removed would be the wrong direction to fail.
    """
    if role_id is None:
        user.store_role_id = None
        db.flush()
        return None
    role = get_role(db, store_id, role_id)
    user.store_role_id = role.id
    set_user_permissions(store_id, user.id, role_matrix(role))
    db.flush()
    return role


def detach_member(db: Session, user: User) -> None:
    """Drop a user's role label without touching their overlay.

    Called when someone edits one member's access by hand: they keep
    the matrix just given to them, and the next role edit will not
    quietly undo it.
    """
    if user.store_role_id is not None:
        user.store_role_id = None
        db.flush()


def delete_role(
    db: Session, store_id: int, role_id: int,
) -> tuple[str, list[User]]:
    """Delete a role. Members keep their current access and simply
    stop being tracked — deleting a label must not change what
    anyone can do.

    Returns the deleted name and the users that were detached.
    """
    role = get_role(db, store_id, role_id)
    detached = members(db, store_id, role.id)
    for user in detached:
        user.store_role_id = None
    name = role.name
    db.flush()
    db.delete(role)
    db.flush()
    return name, detached


__all__ = [
    "MAX_NAME", "RoleError", "RoleNotFoundError", "apply_to_members",
    "assign_role", "create_role", "delete_role", "detach_member",
    "get_role", "list_roles", "member_counts", "members", "role_matrix",
    "update_role",
]
