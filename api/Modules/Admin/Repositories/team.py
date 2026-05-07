"""Team-roster (StoreEmployee) SQL helpers."""
from sqlalchemy.orm import Session

from api.Modules.Admin.Models import StoreEmployee


def list_team(db: Session, store_id: int) -> list[StoreEmployee]:
    """All StoreEmployee rows for one store, sorted by name asc.
    Includes inactive rows so the admin team page can show
    deactivated cashiers + reactivate them; the transfer form's
    `useEmployees()` hook filters to active before rendering its
    dropdown."""
    return (
        db.query(StoreEmployee)
          .filter_by(store_id=store_id)
          .order_by(StoreEmployee.name.asc())
          .all()
    )


def find_team_member(
    db: Session, store_id: int, employee_id: int,
) -> StoreEmployee | None:
    return (
        db.query(StoreEmployee)
          .filter_by(id=employee_id, store_id=store_id)
          .first()
    )
