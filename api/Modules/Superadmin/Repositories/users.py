"""User SQL helpers for superadmin endpoints.

The superadmin has cross-store visibility — these helpers cover
the patterns where simple ``db.get(User, id)`` isn't enough
(joins with Store for display, filters by role, bulk searches).
"""
from typing import Any

from sqlalchemy.orm import Session

from api.Modules.Auth.Models import User


def list_users_in_store(
    db: Session, store_id: int,
) -> list[User]:
    """Every User row pinned to a store, oldest first (matches the
    superadmin store-drill team column ordering)."""
    return (
        db.query(User)
          .filter(User.store_id == store_id)
          .order_by(User.created_at)
          .all()
    )


def list_active_admins_for_store(
    db: Session, store_id: int,
) -> list[User]:
    """Active store admins — the recipients of an "email admin"
    superadmin action. Filters to ``role == 'admin'`` and
    ``is_active``; does NOT filter for email-non-empty (caller
    handles that since the empty case requires a 422 response)."""
    return (
        db.query(User)
          .filter(
              User.store_id == store_id,
              User.role == "admin",
              User.is_active == True,  # noqa: E712 — SQLAlchemy needs == True
          )
          .all()
    )


def count_all_users(db: Session) -> int:
    """Total user count for dashboard KPIs."""
    return db.query(User).count()


def list_users_with_store_query(db: Session) -> Any:
    """Base Query for the cross-store user list — joins User to
    Store (outer, since superadmin/owners have no store_id) so
    the caller can ``.filter()`` + paginate as needed.

    Returns rows of ``(User, store_name)`` tuples — superadmin
    table displays both. Caller is responsible for filtering by
    search term + role + status and applying pagination via
    ``api.Core.Pagination.paginate``.

    Returns ``Any`` because the SQLAlchemy 1.x ``Query[Tuple[...]]``
    generics don't compose cleanly with the bound type expected by
    ``paginate()`` — the caller treats the result as a plain Query
    at runtime."""
    from api.Modules.Tenancy.Models import Store
    return (
        db.query(User, Store.name)
          .outerjoin(Store, User.store_id == Store.id)
          .order_by(User.created_at.desc())
    )
