"""StoreEmployee SQL helpers for time-clock endpoints.

The time-clock module needs a few patterns that don't fit the
Admin Repositories' broader CRUD:
  - bulk fetch of (id → name) for labelling history rows
  - active-only roster for the passkey enrollment list
"""
from sqlalchemy.orm import Session

from api.Modules.Tenancy.Models import StoreEmployee


def get_employee_name_map(
    db: Session, employee_ids: list[int] | set[int],
) -> dict[int, str]:
    """Bulk fetch ``{employee_id: name}``. Returns ``{}`` for
    empty input so callers don't need to guard."""
    if not employee_ids:
        return {}
    rows = (
        db.query(StoreEmployee.id, StoreEmployee.name)
          .filter(StoreEmployee.id.in_(list(employee_ids)))
          .all()
    )
    return {int(sid): str(name or "") for sid, name in rows}


def list_active_employees(
    db: Session, store_id: int,
) -> list[StoreEmployee]:
    """Active StoreEmployee rows for a store, name asc. Used by
    the passkey-enrollment + clock-in roster page."""
    return (
        db.query(StoreEmployee)
          .filter(
              StoreEmployee.store_id == store_id,
              StoreEmployee.is_active == True,  # noqa: E712 — SQLAlchemy needs == True
          )
          .order_by(StoreEmployee.name.asc())
          .all()
    )
