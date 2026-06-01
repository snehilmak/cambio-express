"""Store SQL helpers for superadmin platform-level endpoints.

The superadmin frequently looks up stores by id, slug, or in bulk.
These helpers wrap the most common patterns. Note: ``db.get(Store, id)``
is already a one-liner — we only re-export when the wrapper adds
context (e.g., ordering, plan-filtering, name-only fetch).
"""
from sqlalchemy.orm import Session

from api.Modules.Tenancy.Models import Store


def list_all_stores(db: Session) -> list[Store]:
    """Every store, no filter. Caller decides ordering as needed."""
    return db.query(Store).all()


def list_all_stores_newest_first(db: Session) -> list[Store]:
    """All stores sorted by ``created_at`` desc — the canonical
    superadmin ``/stores`` page order."""
    return db.query(Store).order_by(Store.created_at.desc()).all()


def list_stores_by_ids(
    db: Session, store_ids: list[int],
) -> list[Store]:
    """Bulk fetch by id list. Returns ``[]`` for empty input."""
    if not store_ids:
        return []
    return db.query(Store).filter(Store.id.in_(store_ids)).all()


def get_store_by_slug(
    db: Session, slug: str,
) -> Store | None:
    """One store by slug (unique). Used by the create-store flow
    to check slug uniqueness and the slug-based admin login
    fallback."""
    return (
        db.query(Store)
          .filter(Store.slug == slug)
          .one_or_none()
    )


def count_all_stores(db: Session) -> int:
    """Total store count for the dashboard's ``total_stores`` KPI."""
    return db.query(Store).count()
