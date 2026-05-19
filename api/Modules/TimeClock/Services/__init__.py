"""TimeClock — Services.

Pure functions over ``TimeClockEntry`` — the controller layer
calls these, wraps ``ValueError`` into HTTPException, and
records the audit row. No HTTP concerns leak in here.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

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


class AlreadyOnBreakError(ValueError):
    """Raised when ``start_break`` is called for an entry that's
    already paused."""


class NotOnBreakError(ValueError):
    """Raised when ``end_break`` is called for an entry that
    isn't currently paused."""


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
    # Auto-end any open break — common case is the cashier
    # forgets to tap "End break" and just clocks out. Counts
    # the time-on-break against the running ``break_minutes``
    # total so it doesn't accidentally inflate hours_worked.
    if entry.break_started_at is not None:
        elapsed_break_sec = (now - entry.break_started_at).total_seconds()
        setattr(entry, "break_minutes", round(
            float(entry.break_minutes or 0.0) + elapsed_break_sec / 60, 4,
        ))
        setattr(entry, "break_started_at", None)
    delta = now - entry.clock_in_at
    setattr(entry, "clock_out_at", now)
    setattr(entry, "clock_out_user_id", user_id)
    # Subtract break minutes from the elapsed wall-clock so a
    # 9-to-5 shift with a 60-min lunch records 7.0 hours.
    elapsed_hours = delta.total_seconds() / 3600
    break_hours   = float(entry.break_minutes or 0.0) / 60
    # Round to 4 decimal places (~14 seconds) — enough
    # precision for payroll without floating-point noise.
    entry.hours_worked      = round(max(0.0, elapsed_hours - break_hours), 4)
    if notes_append:
        suffix = (notes_append or "")[:500]
        existing = (entry.notes or "").strip()
        combined = f"{existing}\n{suffix}" if existing else suffix
        setattr(entry, "notes", combined[:500])
    db.flush()
    return entry


def start_break(
    db: Session,
    *,
    store_id: int,
    store_employee_id: int,
) -> TimeClockEntry:
    """Pause the picked roster member's open shift. Sets
    ``break_started_at`` to now. Raises ``NotClockedInError``
    when no shift is open and ``AlreadyOnBreakError`` when
    one's already paused.

    Caller commits.
    """
    emp = _require_roster_member(db, store_id, store_employee_id)
    entry = open_entry_for(db, store_id, store_employee_id)
    if entry is None:
        raise NotClockedInError(
            f"{emp.name} is not currently clocked in — start a "
            "shift before taking a break.",
        )
    if entry.break_started_at is not None:
        raise AlreadyOnBreakError(
            f"{emp.name} is already on break.",
        )
    entry.break_started_at = datetime.utcnow()
    db.flush()
    return entry


def end_break(
    db: Session,
    *,
    store_id: int,
    store_employee_id: int,
) -> TimeClockEntry:
    """Resume the picked roster member's shift. Adds the
    elapsed break time to ``break_minutes`` and clears
    ``break_started_at``. Raises ``NotOnBreakError`` when no
    break is in progress.

    Caller commits.
    """
    emp = _require_roster_member(db, store_id, store_employee_id)
    entry = open_entry_for(db, store_id, store_employee_id)
    if entry is None:
        raise NotClockedInError(
            f"{emp.name} is not currently clocked in.",
        )
    if entry.break_started_at is None:
        raise NotOnBreakError(
            f"{emp.name} is not currently on break.",
        )
    elapsed_sec = (datetime.utcnow() - entry.break_started_at).total_seconds()
    setattr(entry, "break_minutes", round(
        float(entry.break_minutes or 0.0) + elapsed_sec / 60, 4,
    ))
    setattr(entry, "break_started_at", None)
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


# ── Admin CRUD ──────────────────────────────────────────────


class EntryNotFoundError(ValueError):
    """The targeted ``TimeClockEntry`` does not exist or
    belongs to a different store than the caller's JWT scope."""


def _compute_hours(
    clock_in_at: datetime, clock_out_at: datetime | None,
) -> float | None:
    """Mirrors ``clock_out`` math so an admin-edited entry
    matches what a normal punch would produce. Returns None
    when the entry is still open."""
    if clock_out_at is None:
        return None
    delta = clock_out_at - clock_in_at
    return round(delta.total_seconds() / 3600, 4)


def admin_create_entry(
    db: Session,
    *,
    store_id: int,
    store_employee_id: int,
    clock_in_at: datetime,
    clock_out_at: datetime | None,
    notes: str = "",
) -> tuple[TimeClockEntry, str]:
    """Back-fill an entry for the roster member at the given
    timestamps. Used when an operator forgot to punch and the
    admin reconstructs the shift after the fact.

    Returns ``(entry, audit_summary)`` — the controller writes
    the audit row. The summary captures the seed values so the
    later history view can replay how the row got created.

    Caller commits.
    """
    emp = _require_roster_member(db, store_id, store_employee_id)
    if clock_out_at is not None and clock_out_at <= clock_in_at:
        raise ValueError("clock_out_at must be after clock_in_at.")
    entry = TimeClockEntry(
        store_id=store_id,
        store_employee_id=store_employee_id,
        clock_in_at=clock_in_at,
        clock_out_at=clock_out_at,
        hours_worked=_compute_hours(clock_in_at, clock_out_at),
        notes=(notes or "")[:500],
    )
    db.add(entry)
    db.flush()
    hours_str = (
        f"{entry.hours_worked:.2f}h"
        if entry.hours_worked is not None else "open"
    )
    summary = (
        f"Admin create · {emp.name} · "
        f"{clock_in_at.isoformat()} → "
        f"{clock_out_at.isoformat() if clock_out_at else 'open'} "
        f"({hours_str})"
    )
    return entry, summary


# Fields the admin can edit on an existing entry. Anything else
# (store_id, store_employee_id) requires deleting + recreating —
# moving an entry to a different person is a different concept
# than fixing its times.
_ADMIN_EDITABLE_FIELDS: tuple[str, ...] = (
    "clock_in_at", "clock_out_at", "notes", "status",
)


# Allowed values for ``TimeClockEntry.status``. Mirrored by
# the Pydantic ``Literal`` on the request schema.
VALID_STATUSES: tuple[str, ...] = ("pending", "approved", "rejected")


def admin_update_entry(
    db: Session,
    *,
    entry_id: int,
    store_id: int,
    patch: dict[str, Any],
) -> tuple[TimeClockEntry, str]:
    """Apply admin edits to an entry. ``patch`` is a dict keyed
    on the editable fields (``clock_in_at`` / ``clock_out_at``
    as ``datetime`` or None, ``notes`` as str, ``status`` as
    one of ``VALID_STATUSES``). Unknown keys raise ``ValueError``;
    missing keys are left untouched.

    Recomputes ``hours_worked`` whenever either timestamp
    changes (or when the row is opened by clearing
    ``clock_out_at``). Captures a field-level diff in the
    returned summary so the audit view shows what changed.

    Sets ``adjusted=True`` on any non-no-op patch — surfaces the
    "this row was edited" badge in the admin view. A pure
    status-change still counts as an adjustment.

    Caller commits.
    """
    entry = db.get(TimeClockEntry, entry_id)
    if entry is None or entry.store_id != store_id:
        raise EntryNotFoundError(
            "That time-clock entry does not belong to this store.",
        )
    diffs: list[str] = []
    for k, v in patch.items():
        if k not in _ADMIN_EDITABLE_FIELDS:
            raise ValueError(f"Field {k!r} is not admin-editable.")
        if k == "status" and v not in VALID_STATUSES:
            raise ValueError(
                f"status must be one of {VALID_STATUSES!r}.",
            )
        old = getattr(entry, k)
        if old == v:
            continue
        diffs.append(f"{k}: {_fmt(old)} → {_fmt(v)}")
        setattr(entry, k, v)
    # Always re-validate the open<close invariant after the
    # patch — a partial patch could land an out-of-order pair.
    if entry.clock_out_at is not None and entry.clock_out_at <= entry.clock_in_at:
        raise ValueError("clock_out_at must be after clock_in_at.")
    # Recompute hours whenever the times could have changed.
    new_hours = _compute_hours(
        entry.clock_in_at,  # type: ignore[arg-type]
        entry.clock_out_at,  # type: ignore[arg-type]
    )
    if new_hours != entry.hours_worked:
        diffs.append(
            f"hours_worked: {_fmt(entry.hours_worked)} → {_fmt(new_hours)}",
        )
        setattr(entry, "hours_worked", new_hours)
    if diffs:
        # Stamp the "edited after the fact" flag so the
        # admin view's "Adjusted: Yes" badge lights up. A
        # no-op patch leaves the flag alone.
        if not entry.adjusted:
            setattr(entry, "adjusted", True)
    db.flush()
    if not diffs:
        summary = "Admin update · no-op (no fields changed)"
    else:
        summary = "Admin update · " + "; ".join(diffs)
    return entry, summary


def admin_delete_entry(
    db: Session,
    *,
    entry_id: int,
    store_id: int,
) -> tuple[int, str]:
    """Remove an entry. Returns ``(store_employee_id,
    audit_summary)`` so the controller can write the audit row
    against the still-known roster id (the entry's gone after
    commit). Caller commits.
    """
    entry = db.get(TimeClockEntry, entry_id)
    if entry is None or entry.store_id != store_id:
        raise EntryNotFoundError(
            "That time-clock entry does not belong to this store.",
        )
    emp = db.get(StoreEmployee, entry.store_employee_id)
    emp_name = emp.name if emp else f"#{entry.store_employee_id}"
    hours_str = (
        f"{entry.hours_worked:.2f}h"
        if entry.hours_worked is not None else "open"
    )
    summary = (
        f"Admin delete · {emp_name} · "
        f"{entry.clock_in_at.isoformat()} → "
        f"{entry.clock_out_at.isoformat() if entry.clock_out_at else 'open'} "
        f"({hours_str})"
    )
    store_employee_id = int(entry.store_employee_id)
    db.delete(entry)
    db.flush()
    return store_employee_id, summary


def _fmt(value: Any) -> str:
    """Audit-summary formatter — keeps ``None`` legible and
    trims long strings so the audit row stays readable."""
    if value is None:
        return "—"
    if isinstance(value, datetime):
        return value.isoformat()
    s = str(value)
    if len(s) > 60:
        return s[:57] + "…"
    return s


__all__ = [
    "AlreadyClockedInError",
    "AlreadyOnBreakError",
    "EntryNotFoundError",
    "NotClockedInError",
    "NotOnBreakError",
    "RosterEmployeeNotFoundError",
    "admin_create_entry",
    "admin_delete_entry",
    "admin_update_entry",
    "clock_in",
    "clock_out",
    "end_break",
    "entries_for_period",
    "open_entries_for_store",
    "open_entry_for",
    "start_break",
]
