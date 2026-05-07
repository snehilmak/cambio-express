"""Team-roster Service.

CRUD operations on StoreEmployee. Per the model docstring,
admins deactivate (never delete) entries so historical
attribution survives — `delete` here is a soft-delete that
flips is_active.
"""
from sqlalchemy.orm import Session

from api.Modules.Admin.Models import StoreEmployee


class TeamMemberNotFoundError(LookupError):
    pass


def add_team_member(
    db: Session, store_id: int, name: str,
) -> StoreEmployee:
    """Insert a new active StoreEmployee row. Caller commits.
    Trims + truncates the name to fit the column."""
    name = (name or "").strip()[:120]
    if not name:
        raise ValueError("Name is required.")
    row = StoreEmployee(
        store_id=store_id,
        name=name,
        is_active=True,
    )
    db.add(row)
    db.flush()
    return row


def update_team_member(
    db: Session, employee: StoreEmployee,
    *, name: str | None = None, is_active: bool | None = None,
) -> StoreEmployee:
    """Rename and/or toggle active. Caller commits."""
    if name is not None:
        name = name.strip()[:120]
        if not name:
            raise ValueError("Name cannot be blank.")
        employee.name = name
    if is_active is not None:
        employee.is_active = bool(is_active)
    db.flush()
    return employee


def deactivate_team_member(
    db: Session, employee: StoreEmployee,
) -> StoreEmployee:
    """Soft-delete: flip is_active=False. We never hard-delete
    StoreEmployee rows so the historical employee_name + employee_id
    attribution on past Transfer rows survives."""
    employee.is_active = False
    db.flush()
    return employee
