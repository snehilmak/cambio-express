"""Owner connect-code SQL helpers.

Pure query functions for OwnerConnectCode rows. Business logic
(revoke validation, audit logging, code generation) stays in the
Controller / Service layers — this module only does reads + scoped
filters.
"""
from sqlalchemy.orm import Session

from api.Modules.Tenancy.Models import OwnerConnectCode, Store


def list_codes_for_owner(
    db: Session, owner_id: int,
) -> list[OwnerConnectCode]:
    """Every code minted by an owner, newest first (active +
    redeemed + revoked + expired)."""
    return (
        db.query(OwnerConnectCode)
          .filter(OwnerConnectCode.owner_id == owner_id)
          .order_by(OwnerConnectCode.created_at.desc())
          .all()
    )


def find_owner_code(
    db: Session, code_id: int, owner_id: int,
) -> OwnerConnectCode | None:
    """One specific code belonging to this owner. Returns None
    when the id doesn't match or the code belongs to a different
    owner (no cross-owner enumeration leak)."""
    return (
        db.query(OwnerConnectCode)
          .filter(
              OwnerConnectCode.id == code_id,
              OwnerConnectCode.owner_id == owner_id,
          )
          .one_or_none()
    )


def get_store_names_map(
    db: Session, store_ids: list[int],
) -> dict[int, str]:
    """Bulk fetch store names for a list of ids. Used to label
    redeemed codes with the store they linked to."""
    if not store_ids:
        return {}
    return {
        int(s.id): str(s.name or "")
        for s in db.query(Store).filter(Store.id.in_(store_ids)).all()
    }
