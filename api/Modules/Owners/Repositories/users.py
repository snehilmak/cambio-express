"""User SQL helpers for owner umbrella queries.

Owners enumerate users across all stores they're linked to. The
search pattern (name + username ilike) lives here so it can be
reused by other umbrella views (audit, reports, etc.) without
copy-pasting the LIKE construction.
"""
from sqlalchemy.orm import Query, Session

from api.Modules.Auth.Models import User


def users_in_stores_query(
    db: Session,
    store_ids: list[int],
    *,
    search: str = "",
) -> "Query[User]":
    """Build a User query scoped to a set of store_ids with an
    optional name/username substring search.

    Returns the SQLAlchemy Query (not a list) so the caller can
    apply pagination via ``api.Core.Pagination.paginate`` or count
    before slicing.
    """
    query = db.query(User).filter(User.store_id.in_(store_ids))
    needle = search.strip()
    if needle:
        like = f"%{needle}%"
        query = query.filter(
            User.username.ilike(like) | User.full_name.ilike(like)
        )
    return query.order_by(User.store_id, User.full_name)
