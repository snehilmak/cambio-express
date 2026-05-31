"""Store↔Owner link SQL helpers.

StoreOwnerLink is the join table connecting owners to the stores
in their umbrella. Reads are scoped here; writes (link/unlink)
stay in the Controller because they're tied to audit logging.
"""
from sqlalchemy.orm import Session

from api.Modules.Tenancy.Models import StoreOwnerLink


def find_link(
    db: Session, owner_id: int, store_id: int,
) -> StoreOwnerLink | None:
    """The link row for a specific (owner, store) pair, or None."""
    return (
        db.query(StoreOwnerLink)
          .filter(
              StoreOwnerLink.owner_id == owner_id,
              StoreOwnerLink.store_id == store_id,
          )
          .one_or_none()
    )
