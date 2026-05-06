"""User lookup helpers.

The User table mixes per-store users (admin / employee / owner) with
the platform-wide superadmin (`store_id IS NULL`). The unique
constraint is `(store_id, username)` — the same email can be a
user at multiple stores. Login flows must always know which store
the request is for; we never search "username across all stores".
"""
from typing import Iterable

from sqlalchemy.orm import Session

from api.Modules.Auth.Models import User


def find_user_by_id(db: Session, user_id: int) -> User | None:
    """Lookup by primary key. Used for session restoration and the
    JWT subject resolution path."""
    return db.get(User, user_id)


def find_user_by_username_in_store(
    db: Session, store_id: int | None, username: str,
) -> User | None:
    """Find a user by `(store_id, username)`. Pass `store_id=None`
    to look up the superadmin (which lives at `store_id IS NULL`).

    `username` is matched case-sensitively, mirroring the legacy
    behavior — clients normalize to lowercase before submitting.
    """
    if not username:
        return None
    return (
        db.query(User)
          .filter(User.store_id.is_(store_id) if store_id is None
                   else User.store_id == store_id)
          .filter(User.username == username)
          .first()
    )


def find_user_by_username(
    db: Session, username: str, *, role: str | None = None,
) -> User | None:
    """Find a user by username across stores — first match wins.
    Only safe for use in superadmin-style flows (e.g. password reset
    by username) where the caller has already established intent.
    Optional `role` filter scopes to a single role (e.g. "superadmin")
    so a normal user can't be promoted by accident."""
    if not username:
        return None
    q = db.query(User).filter(User.username == username)
    if role:
        q = q.filter(User.role == role)
    return q.first()


def list_users_in_store(
    db: Session, store_id: int, *,
    roles: Iterable[str] | None = None,
    active_only: bool = False,
) -> list[User]:
    """All users in a store, ordered by id asc (insertion order =
    historical seniority). Filter by role(s) and `active_only=True`
    to restrict the set."""
    q = db.query(User).filter(User.store_id == store_id)
    if roles is not None:
        q = q.filter(User.role.in_(list(roles)))
    if active_only:
        q = q.filter(User.is_active.is_(True))
    return q.order_by(User.id.asc()).all()
