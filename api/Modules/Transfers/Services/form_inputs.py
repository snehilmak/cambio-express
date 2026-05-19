"""Transfer-form input parsers + roster helpers.

Three small helpers that pre-process the transfer form fields
before the route stores them on a `Transfer` row:

  - `parse_dob(raw)` — accepts a `YYYY-MM-DD` string, returns
    `date | None`. Blank or malformed input yields None so the
    route can store NULL rather than crash on bad client data.

  - `active_roster(db, store_id)` — every active StoreEmployee
    on the roster, sorted alphabetically. Used to populate the
    "Processed by" dropdown. Inactive employees are hidden so
    cashiers can't credit new transfers to former employees.

  - `pick_employee(db, store_id, raw_id)` — resolve a form
    `employee_id` value against the store's roster. Rejects
    cross-store picks. Returns `(employee_or_none, display_name)`.
"""
from datetime import date, datetime

from sqlalchemy.orm import Session
from typing import Any


def parse_dob(raw: str | None) -> date | None:
    """Parse a `YYYY-MM-DD` date string from the form. Blank /
    malformed input returns None so the caller can store NULL
    rather than crash on bad client data.
    """
    if not raw:
        return None
    try:
        return datetime.strptime(raw, "%Y-%m-%d").date()
    except ValueError:
        return None


def active_roster(db: Session, store_id: int) -> list[Any]:
    """Names available in the "Processed by" dropdown.

    Inactive roster rows are hidden so cashiers can't credit
    new transfers to former employees.
    """
    from api.Modules.Tenancy.Models import StoreEmployee
    return (
        db.query(StoreEmployee)
          .filter_by(store_id=store_id, is_active=True)
          .order_by(StoreEmployee.name.asc())
          .all()
    )


def pick_employee(
    db: Session, store_id: int, raw_id,
) -> tuple:
    """Resolve a form `employee_id` value against the store's
    roster.

    Returns `(employee_or_none, display_name)`. Cross-store
    picks are rejected (the SQL filters on store_id), so a
    cashier from another store can't be credited.

    Bad input (non-int, blank) returns `(None, "")` so the
    route can flash an error.
    """
    from api.Modules.Tenancy.Models import StoreEmployee
    try:
        eid = int(raw_id) if raw_id else None
    except (TypeError, ValueError):
        return None, ""
    if not eid:
        return None, ""
    emp = (
        db.query(StoreEmployee)
          .filter_by(id=eid, store_id=store_id)
          .first()
    )
    return (emp, emp.name) if emp else (None, "")
