"""TimeClock — Services.

Pure functions over ``TimeClockEntry`` — the controller layer
calls these, wraps ``ValueError`` into HTTPException, and
records the audit row. No HTTP concerns leak in here.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from api.Modules.TimeClock.Models import TimeClockEntry
from api.Modules.Tenancy.Models import StoreEmployee


# ── Exceptions ──────────────────────────────────────────────


class AlreadyClockedInError(ValueError):
    """Raised when ``clock_in`` is called for an employee who
    already has an open shift."""


class NotClockedInError(ValueError):
    """Raised when ``clock_out`` is called for an employee with
    no open shift."""


class RosterEmployeeNotFoundError(ValueError):
    """Raised when the picked ``store_employee_id`` doesn't
    belong to the store on the JWT — keeps a malicious POST
    from clocking somebody at another store."""


# ── Public API ──────────────────────────────────────────────


def open_entry_for(
    db: Session, store_id: int, store_employee_id: int,
) -> Optional[TimeClockEntry]:
    """Return the currently-open ``TimeClockEntry`` for the
    given employee, or None. Open == ``clock_out_at IS NULL``.
    Uses the ``(store_employee_id, clock_out_at)`` composite
    index — one probe."""
    return (
        db.query(TimeClockEntry)
          .filter(
              TimeClockEntry.store_id == store_id,
              TimeClockEntry.store_employee_id == store_employee_id,
              TimeClockEntry.clock_out_at.is_(None),
          )
          .one_or_none()
    )


def open_entries_for_store(
    db: Session, store_id: int,
) -> list[TimeClockEntry]:
    """Every currently-open shift at the store, ordered by
    ``clock_in_at`` ascending. Powers the "who's on the clock
    right now?" status panel."""
    return (
        db.query(TimeClockEntry)
          .filter(
              TimeClockEntry.store_id == store_id,
              TimeClockEntry.clock_out_at.is_(None),
          )
          .order_by(TimeClockEntry.clock_in_at.asc())
          .all()
    )


def clock_in(
    db: Session,
    *,
    store_id: int,
    store_employee_id: int,
    user_id: int | None,
    notes: str = "",
) -> TimeClockEntry:
    """Open a new shift for the picked roster member.

    Validates the store_employee_id belongs to ``store_id``
    (cross-tenant punch attempts → ``RosterEmployeeNotFoundError``)
    and that no open entry exists for them yet
    (``AlreadyClockedInError``).

    Caller commits.
    """
    emp = _require_roster_member(db, store_id, store_employee_id)
    existing = open_entry_for(db, store_id, store_employee_id)
    if existing is not None:
        raise AlreadyClockedInError(
            f"{emp.name} is already clocked in.",
        )
    entry = TimeClockEntry(
        store_id=store_id,
        store_employee_id=store_employee_id,
        clock_in_user_id=user_id,
        clock_in_at=datetime.utcnow(),
        notes=(notes or "")[:500],
    )
    db.add(entry)
    db.flush()
    return entry


def clock_out(
    db: Session,
    *,
    store_id: int,
    store_employee_id: int,
    user_id: int | None,
    notes_append: str = "",
) -> TimeClockEntry:
    """Close the currently-open shift for the picked roster
    member. Computes ``hours_worked`` (UTC-subtracted; the
    same delta in any timezone). Raises
    ``NotClockedInError`` if nothing's open.

    Notes from clock-out get appended to the entry — clock-in
    notes survive (the operator can leave context at the start
    AND end of the shift).

    Caller commits.
    """
    emp = _require_roster_member(db, store_id, store_employee_id)
    entry = open_entry_for(db, store_id, store_employee_id)
    if entry is None:
        raise NotClockedInError(
            f"{emp.name} is not currently clocked in.",
        )
    now = datetime.utcnow()
    delta = now - entry.clock_in_at
    entry.clock_out_at      = now
    entry.clock_out_user_id = user_id
    # Round to 4 decimal places (~14 seconds) — enough
    # precision for payroll without floating-point noise.
    entry.hours_worked      = round(delta.total_seconds() / 3600, 4)
    if notes_append:
        suffix = (notes_append or "")[:500]
        existing = (entry.notes or "").strip()
        combined = f"{existing}\n{suffix}" if existing else suffix
        entry.notes = combined[:500]
    db.flush()
    return entry


def entries_for_period(
    db: Session,
    *,
    store_id: int,
    start: datetime,
    end: datetime,
    store_employee_id: int | None = None,
) -> list[TimeClockEntry]:
    """Closed + open shifts that overlap the [start, end)
    window. Ordered by ``clock_in_at`` desc so the most recent
    entries come first (matches the admin payroll view's
    expected reading order).

    Filters on ``clock_in_at`` only — a shift that started
    inside the window but hasn't closed yet still shows up,
    same as it does on the live status panel. Payroll
    consumers should treat open entries as "in progress" and
    exclude them from settled totals.
    """
    q = db.query(TimeClockEntry).filter(
        TimeClockEntry.store_id == store_id,
        TimeClockEntry.clock_in_at >= start,
        TimeClockEntry.clock_in_at < end,
    )
    if store_employee_id is not None:
        q = q.filter(
            TimeClockEntry.store_employee_id == store_employee_id,
        )
    return q.order_by(TimeClockEntry.clock_in_at.desc()).all()


# ── Internal helpers ────────────────────────────────────────


def _require_roster_member(
    db: Session, store_id: int, store_employee_id: int,
) -> StoreEmployee:
    emp = db.get(StoreEmployee, store_employee_id)
    if emp is None or emp.store_id != store_id:
        raise RosterEmployeeNotFoundError(
            "That roster member doesn't belong to this store.",
        )
    if not emp.is_active:
        raise RosterEmployeeNotFoundError(
            f"{emp.name} is deactivated — reactivate them in "
            "Settings → Team before clocking in.",
        )
    return emp


__all__ = [
    "AlreadyClockedInError",
    "NotClockedInError",
    "RosterEmployeeNotFoundError",
    "clock_in",
    "clock_out",
    "entries_for_period",
    "open_entries_for_store",
    "open_entry_for",
]
