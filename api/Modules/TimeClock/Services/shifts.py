"""Shift scheduling — pure helpers over ``TimeClockShift``.

The controller layer calls these, wraps ``ValueError`` /
``ShiftNotFoundError`` into HTTPException, records the audit
row.  No HTTP concerns leak in here.

Shifts are decoupled from punches: a cashier can clock in
without a planned shift, and a planned shift without a matching
punch is a no-show.  v1 ships data + CRUD only; the
late-arrival / no-show derivation against ``TimeClockEntry`` is
a follow-up that joins these two tables at read time.
"""
from __future__ import annotations

from datetime import date, time
from typing import Optional

from sqlalchemy.orm import Session

from api.Modules.TimeClock.Models import TimeClockShift
from api.Modules.Tenancy.Models import StoreEmployee


class ShiftNotFoundError(ValueError):
    """Raised when a CRUD call targets a shift id that doesn't
    belong to the JWT's store — keeps a tampered POST from
    editing another store's schedule."""


class RosterEmployeeNotFoundError(ValueError):
    """The picked ``store_employee_id`` doesn't belong to the
    store on the JWT.  Same name as the punch-flow exception
    intentionally — the controller layer maps both to a 422 with
    the same message."""


def _ensure_roster_in_store(
    db: Session, store_id: int, store_employee_id: int,
) -> None:
    found = (
        db.query(StoreEmployee.id)
          .filter(
              StoreEmployee.store_id == store_id,
              StoreEmployee.id == store_employee_id,
          )
          .first()
    )
    if found is None:
        raise RosterEmployeeNotFoundError(
            "That roster member isn't on this store's team.",
        )


def _validate_times(start_time: time, end_time: time) -> None:
    """Reject zero-length or backwards shifts.

    Overnight shifts (cross-midnight) are not v1 — the
    ``shift_date`` + same-day ``end_time`` model can't represent
    them cleanly.  A planned overnight is split into two rows
    (one ending at 23:59, one starting at 00:00 the next day)
    until we have a real "spans midnight" follow-up.
    """
    if end_time <= start_time:
        raise ValueError(
            "End time must be after start time. Split overnight "
            "shifts into two rows (one per calendar day).",
        )


def shifts_for_period(
    db: Session,
    *,
    store_id: int,
    start: date,
    end: date,
    store_employee_id: Optional[int] = None,
) -> list[TimeClockShift]:
    """Shifts with ``shift_date`` in ``[start, end)`` for the
    store.  Half-open window matches the payroll history pattern
    so a "May 1 - May 14" biweekly window is
    ``start=May 1, end=May 15``.
    """
    q = (
        db.query(TimeClockShift)
          .filter(
              TimeClockShift.store_id == store_id,
              TimeClockShift.shift_date >= start,
              TimeClockShift.shift_date <  end,
          )
    )
    if store_employee_id is not None:
        q = q.filter(
            TimeClockShift.store_employee_id == store_employee_id,
        )
    return (
        q.order_by(
            TimeClockShift.shift_date.asc(),
            TimeClockShift.start_time.asc(),
        )
        .all()
    )


def create_shift(
    db: Session,
    *,
    store_id: int,
    store_employee_id: int,
    shift_date: date,
    start_time: time,
    end_time: time,
    notes: str = "",
    created_by_user_id: Optional[int] = None,
) -> TimeClockShift:
    _ensure_roster_in_store(db, store_id, store_employee_id)
    _validate_times(start_time, end_time)
    row = TimeClockShift(
        store_id=store_id,
        store_employee_id=store_employee_id,
        shift_date=shift_date,
        start_time=start_time,
        end_time=end_time,
        notes=notes or "",
        created_by_user_id=created_by_user_id,
    )
    db.add(row)
    db.flush()
    return row


def update_shift(
    db: Session,
    *,
    store_id: int,
    shift_id: int,
    store_employee_id: Optional[int] = None,
    shift_date: Optional[date] = None,
    start_time: Optional[time] = None,
    end_time: Optional[time] = None,
    notes: Optional[str] = None,
) -> TimeClockShift:
    row = (
        db.query(TimeClockShift)
          .filter(
              TimeClockShift.id == shift_id,
              TimeClockShift.store_id == store_id,
          )
          .first()
    )
    if row is None:
        raise ShiftNotFoundError(
            f"No shift {shift_id} on this store's schedule.",
        )
    if store_employee_id is not None:
        _ensure_roster_in_store(db, store_id, store_employee_id)
        row.store_employee_id = store_employee_id
    if shift_date is not None:
        row.shift_date = shift_date
    # Validate the candidate start/end against the merged values
    # so a partial update can't sneak in a zero-length shift.
    candidate_start = start_time if start_time is not None else row.start_time
    candidate_end   = end_time   if end_time   is not None else row.end_time
    if start_time is not None or end_time is not None:
        _validate_times(candidate_start, candidate_end)
        row.start_time = candidate_start
        row.end_time   = candidate_end
    if notes is not None:
        row.notes = notes
    db.flush()
    return row


def delete_shift(
    db: Session, *, store_id: int, shift_id: int,
) -> None:
    row = (
        db.query(TimeClockShift)
          .filter(
              TimeClockShift.id == shift_id,
              TimeClockShift.store_id == store_id,
          )
          .first()
    )
    if row is None:
        raise ShiftNotFoundError(
            f"No shift {shift_id} on this store's schedule.",
        )
    db.delete(row)
    db.flush()
