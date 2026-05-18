"""Pydantic request / response schemas for the TimeClock module."""
from pydantic import BaseModel, ConfigDict, Field


class ClockPunchRequest(BaseModel):
    """Body for ``/timeclock/clock-in`` and
    ``/timeclock/clock-out``. Both use the same shape — the
    operator picks a roster member and optionally adds a note."""

    model_config = ConfigDict(extra="forbid")

    store_employee_id: int = Field(..., ge=1)
    notes:             str = Field("", max_length=500)


class TimeClockEntryRow(BaseModel):
    """One shift row. ``clock_out_at`` / ``hours_worked`` are
    None while the shift is in progress."""

    model_config = ConfigDict(extra="forbid")

    id:                int
    store_employee_id: int
    employee_name:     str
    clock_in_at:       str  # ISO-8601 UTC
    clock_out_at:      str | None = None
    hours_worked:      float | None = None
    notes:             str = ""


class TimeClockStatusResponse(BaseModel):
    """Live "who's on the clock right now?" payload for the
    punch page. Returns every open entry at the user's store
    so a cashier can see if their name is already punched
    before clicking Clock In."""

    model_config = ConfigDict(extra="forbid")

    open_entries: list[TimeClockEntryRow]


class TimeClockPunchResponse(BaseModel):
    """Returned by both clock-in and clock-out — the freshly-
    modified entry. Keeps the SPA from needing a follow-up
    GET to refresh the row."""

    model_config = ConfigDict(extra="forbid")

    entry: TimeClockEntryRow


class TimeClockEntryList(BaseModel):
    """Payroll history page — paginated by date range, not
    cursor (a single biweekly window for a store is small)."""

    model_config = ConfigDict(extra="forbid")

    rows: list[TimeClockEntryRow]
    # Aggregated total ``hours_worked`` across closed rows in
    # the window. Open entries don't count.
    total_hours: float
