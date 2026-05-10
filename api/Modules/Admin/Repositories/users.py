"""Per-store users (User table) SQL helpers.

These power /api/v2/admin/users — the React SPA roster + create/
edit forms. Lookups are always store-scoped: a User's per-store
identity is `(store_id, username)` (unique constraint), so any
admin operating on someone else's store is a 404, never a 200.
"""
from sqlalchemy.orm import Session

from api.Modules.Admin.Models import User


def list_store_users(db: Session, store_id: int) -> list[User]:
    """All User rows for one store. Sorted by created_at asc to
    mirror the legacy `User.query.filter_by(store_id=sid).all()`
    iteration order (which is insert-order on SQLite + an indexed
    table scan on Postgres). Includes inactive rows so the admin
    can reactivate them from the Edit page."""
    return (
        db.query(User)
          .filter_by(store_id=store_id)
          .order_by(User.created_at.asc(), User.id.asc())
          .all()
    )


def find_store_user(
    db: Session, store_id: int, user_id: int,
) -> User | None:
    """Single User row in this store, or None for cross-store /
    missing IDs — both surface as 404 from the controller so we
    don't leak the existence of unrelated users."""
    return (
        db.query(User)
          .filter_by(id=user_id, store_id=store_id)
          .first()
    )


def find_store_user_by_username(
    db: Session, store_id: int, username: str,
) -> User | None:
    """Used by the create endpoint to detect duplicate usernames
    inside the same store. Cross-store collisions are allowed —
    the unique constraint is `(store_id, username)`."""
    return (
        db.query(User)
          .filter_by(store_id=store_id, username=username)
          .first()
    )
