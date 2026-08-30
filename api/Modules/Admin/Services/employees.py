"""Unified Employees hub — Service (E-1).

One place manages the PERSON: the ``StoreEmployee`` row is the HR
record (payroll basics, personal details, attribution identity);
an optional 1:1 ``user_id`` link attaches their login account.
This service owns the link lifecycle and the HR-field updates;
name/rate/active stay in ``team.py`` (shared with the legacy
Team endpoints until the SPA cutover completes).

Link invariants:
  * a User links to at most one StoreEmployee (DB-unique), and
    only within the same store — cross-store links are tenancy
    violations and raise;
  * only store roles (admin / employee) are linkable — owners and
    platform roles have no HR record at a store;
  * linking never mutates the User row (auth stays auth).
"""
from datetime import date

from sqlalchemy.orm import Session

from api.Modules.Tenancy.Models import StoreEmployee, User

PAYROLL_SCHEDULES = ("", "weekly", "biweekly", "semimonthly", "monthly")
_LINKABLE_ROLES = ("admin", "employee")


class EmployeeLinkError(ValueError):
    """Raised when a login link would violate an invariant."""


def update_employee_hr(
    db: Session, employee: StoreEmployee,
    *,
    hired_on: date | None = None,
    date_of_birth: date | None = None,
    email: str | None = None,
    phone: str | None = None,
    address_line1: str | None = None,
    address_line2: str | None = None,
    payroll_schedule: str | None = None,
    clear_hired_on: bool = False,
    clear_date_of_birth: bool = False,
) -> StoreEmployee:
    """PATCH-style HR-field update. ``None`` = unchanged; the two
    ``clear_*`` flags reset the nullable dates (a date field can't
    use None as its clear sentinel). Caller commits."""
    if clear_hired_on:
        employee.hired_on = None
    elif hired_on is not None:
        employee.hired_on = hired_on
    if clear_date_of_birth:
        employee.date_of_birth = None
    elif date_of_birth is not None:
        employee.date_of_birth = date_of_birth
    if email is not None:
        employee.email = email.strip()[:255]
    if phone is not None:
        employee.phone = phone.strip()[:40]
    if address_line1 is not None:
        employee.address_line1 = address_line1.strip()[:255]
    if address_line2 is not None:
        employee.address_line2 = address_line2.strip()[:255]
    if payroll_schedule is not None:
        schedule = payroll_schedule.strip().lower()
        if schedule not in PAYROLL_SCHEDULES:
            raise ValueError(
                "Payroll schedule must be one of: "
                + ", ".join(s for s in PAYROLL_SCHEDULES if s)
                + " (or empty).",
            )
        employee.payroll_schedule = schedule
    db.flush()
    return employee


def link_employee_user(
    db: Session, store_id: int, employee: StoreEmployee, user_id: int,
) -> StoreEmployee:
    """Attach a login account to this person. Caller commits."""
    user = db.get(User, int(user_id))
    if user is None or user.store_id != store_id:
        # Opaque: cross-store ids look identical to unknown ids.
        raise EmployeeLinkError("User not found on this store.")
    if (user.role or "") not in _LINKABLE_ROLES:
        raise EmployeeLinkError(
            "Only store admin/employee logins can be linked.",
        )
    existing = (
        db.query(StoreEmployee)
        .filter(StoreEmployee.user_id == user.id)
        .first()
    )
    if existing is not None and existing.id != employee.id:
        raise EmployeeLinkError(
            "That login is already linked to another employee.",
        )
    employee.user_id = user.id
    db.flush()
    return employee


def unlink_employee_user(
    db: Session, employee: StoreEmployee,
) -> StoreEmployee:
    """Detach the login. The User account itself is untouched —
    deactivate it separately if the person should lose access."""
    employee.user_id = None
    db.flush()
    return employee


def list_employees_unified(
    db: Session, store_id: int,
) -> tuple[list[tuple[StoreEmployee, User | None]], list[User]]:
    """The hub listing: every HR record (with its linked login, if
    any) plus every store login that has NO HR record yet
    ("login-only" — surfaced so nothing is invisible; the UI
    offers Link / Create-record actions)."""
    rows = (
        db.query(StoreEmployee, User)
        .outerjoin(User, StoreEmployee.user_id == User.id)
        .filter(StoreEmployee.store_id == store_id)
        .order_by(StoreEmployee.name)
        .all()
    )
    linked_ids = {u.id for _, u in rows if u is not None}
    q = (
        db.query(User)
        .filter(
            User.store_id == store_id,
            User.role.in_(_LINKABLE_ROLES),
        )
    )
    if linked_ids:
        q = q.filter(~User.id.in_(linked_ids))
    login_only = q.order_by(User.username).all()
    return [(e, u) for e, u in rows], login_only
