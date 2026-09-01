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
  * LINKING never mutates the User row (auth stays auth).

Editing a linked employee's email or phone is the one exception,
and it is deliberate. Those two fields ARE the login identifier
(L-2), and they were stored on both rows: an admin who corrected
someone's email on the Profile tab updated the HR record while the
person went on signing in with the old one, with nothing anywhere
saying so. ``sync_login_identity`` pushes the change through to
the login, validating and checking for collisions BEFORE writing
either row so a rejected edit leaves both untouched. It changes
the string someone types, not who they are or what they can do —
so it audits but does not revoke sessions.
"""
from datetime import date

from sqlalchemy.orm import Session

from api.Modules.Tenancy.Models import StoreEmployee, User

PAYROLL_SCHEDULES = ("", "weekly", "biweekly", "semimonthly", "monthly")
_LINKABLE_ROLES = ("admin", "employee")


class EmployeeLinkError(ValueError):
    """Raised when a login link would violate an invariant."""


class LoginSyncError(ValueError):
    """The HR edit would break how the linked person signs in."""


def sync_login_identity(
    db: Session, employee: StoreEmployee, *,
    email: str | None, phone: str | None,
) -> tuple[str, str] | None:
    """Push an employee's email/phone onto their LINKED login.

    Email and phone are the login identifier (L-2) and were being
    stored in two places: editing them on the Employees → Profile
    tab updated the HR row and left the login untouched, so the
    person kept signing in with the old address and nothing said
    so. This is the sync half of that fix.

    Returns ``(old_identifier, new_identifier)`` when the login
    actually moved, else ``None``. Raises before writing ANYTHING
    if the result would be invalid or collide — a half-applied
    identity change is worse than a refused one.

    No session revocation: the person and their permissions are
    unchanged, only the string they type. The caller audits it.
    """
    if employee.user_id is None:
        return None
    if email is None and phone is None:
        return None

    from api.Modules.Auth.Services.identity import (
        is_email, login_identifier, normalize_email, normalize_phone,
    )
    from api.Modules.Admin.Repositories.users import (
        find_store_user_by_username,
    )

    user = db.get(User, int(employee.user_id))
    if user is None:
        return None

    # Unspecified fields keep whatever the login already has, so a
    # phone-only edit cannot wipe someone's email.
    new_email = (
        normalize_email(email) if email is not None
        else normalize_email(user.email or "")
    )
    new_phone = (
        (phone or "").strip() if phone is not None
        else (user.phone or "").strip()
    )

    if new_email and not is_email(new_email):
        raise LoginSyncError("Enter a valid email address.")
    if new_phone and not normalize_phone(new_phone):
        raise LoginSyncError("Enter a valid phone number.")

    identifier = login_identifier(new_email, new_phone)
    if not identifier:
        raise LoginSyncError(
            "This person signs in with their email or phone — "
            "clearing both would lock them out. Unlink their login "
            "first if that is what you want.",
        )

    old = user.username or ""
    if identifier == old:
        # Still write the fields: the display values can differ from
        # the identifier (a reformatted phone, a changed email when
        # phone is the identifier).
        user.email = new_email
        user.set_login_phone(new_phone)
        db.flush()
        return None

    clash = find_store_user_by_username(db, employee.store_id, identifier)
    if clash is not None and clash.id != user.id:
        raise LoginSyncError(
            "Someone at this store already signs in with that "
            "email or phone number.",
        )

    user.username = identifier
    user.email = new_email
    user.set_login_phone(new_phone)
    db.flush()
    return old, identifier


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
