"""Store-scoped SQL helpers used across owner endpoints.

Owner endpoints frequently need to:
  - look up a single store by id (drill-down, settings, transfers)
  - bulk-fetch store names for a list of ids (for response labels)

Both patterns are extracted here so the Controllers don't repeat
the same ``db.query(Store).filter(...)`` boilerplate.
"""
from sqlalchemy.orm import Session

from api.Modules.Tenancy.Models import Store


def get_store(db: Session, store_id: int) -> Store | None:
    """One store by primary key, or None."""
    return db.get(Store, store_id)


def get_store_names_map(
    db: Session, store_ids: list[int] | set[int],
) -> dict[int, str]:
    """Bulk fetch ``{store_id: name}`` for a set of ids.
    Returns ``{}`` for an empty input so callers don't need to
    guard before calling."""
    if not store_ids:
        return {}
    return {
        int(s.id): str(s.name or "")
        for s in db.query(Store).filter(Store.id.in_(list(store_ids))).all()
    }


def list_stores_by_ids(
    db: Session, store_ids: list[int],
) -> list[Store]:
    """Bulk fetch Store rows for a set of ids, name-ordered — the
    umbrella views render these as store cards / P&L columns.
    Returns ``[]`` for an empty input so callers don't guard."""
    if not store_ids:
        return []
    return (
        db.query(Store)
          .filter(Store.id.in_(store_ids))
          .order_by(Store.name)
          .all()
    )
