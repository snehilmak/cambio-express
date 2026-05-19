"""Pydantic request / response schemas for the TimeClock module."""
from datetime import date as _date, time as _time
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


# Mirrored from ``Services.VALID_STATUSES`` — kept here as a
# Literal so OpenAPI surfaces the choices to the SPA's
# generated types.
TimeClockStatus = Literal["pending", "approved", "rejected"]


class ClockPunchRequest(BaseModel):
    """Body for ``/timeclock/clock-in`` and
    ``/timeclock/clock-out``. Both use the same shape — the
    operator picks a roster member and optionally adds a note.

    ``assert_token`` + ``assertion`` carry the WebAuthn
    authentication round-trip when the store has
    ``timeclock_require_passkey`` turned on. Both are optional
    at the schema level (so a store that doesn't require
    passkeys keeps the simple body) — the server promotes the
    check to "required" based on the store's toggle."""

    model_config = ConfigDict(extra="forbid")

    store_employee_id: int = Field(..., ge=1)
    notes:             str = Field("", max_length=500)
    assert_token:      str | None = Field(None, max_length=2000)
    assertion:         dict[str, Any] | None = None
    # Browser geolocation — required when the store has
    # ``timeclock_require_geofence`` on. Tight bounds catch
    # garbage from a tampered client. Optional at the schema
    # layer; the server promotes to "required" based on the
    # store toggle.
    geo_lat: float | None = Field(None, ge=-90, le=90)
    geo_lng: float | None = Field(None, ge=-180, le=180)


class TimeClockEntryRow(BaseModel):
    """One shift row. ``clock_out_at`` / ``hours_worked`` are
    None while the shift is in progress.

    Break tracking: ``break_started_at`` is non-null while the
    cashier is on break; ``break_minutes`` is the running
    total accumulated across pause/resume cycles. The
    ``hours_worked`` value at clock-out already subtracts
    ``break_minutes``."""

    model_config = ConfigDict(extra="forbid")

    id:                int
    store_employee_id: int
    employee_name:     str
    clock_in_at:       str  # ISO-8601 UTC
    clock_out_at:      str | None = None
    hours_worked:      float | None = None
    notes:             str = ""
    status:            TimeClockStatus = "pending"
    adjusted:          bool = False
    break_started_at:  str | None = None
    break_minutes:     float = 0.0
    # Late-arrival pill: minutes ``clock_in_at`` lagged the
    # matching ``TimeClockShift.start_time`` in store-local time.
    # Negative = early, 0 = on the dot, None = no planned shift
    # to compare against (admin back-fill or unscheduled punch).
    # The SPA only flags as "late" when this exceeds
    # ``Store.timeclock_late_minutes_threshold``.
    late_minutes:      int | None = None


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
    cursor (a single biweekly window for a store is small).

    ``total_hours`` is every closed shift; ``approved_hours``
    + ``pending_hours`` split that total by status so the SPA
    can render distinct headline KPIs (the inspiration shows
    Scheduled / Spend / Remaining; we ship Approved / Pending
    / Total since shift scheduling is a separate v2 item).
    """

    model_config = ConfigDict(extra="forbid")

    rows: list[TimeClockEntryRow]
    # Aggregated total ``hours_worked`` across closed rows in
    # the window. Open entries don't count.
    total_hours:    float
    approved_hours: float = 0.0
    pending_hours:  float = 0.0
    # Lateness threshold from the store config — the SPA only
    # surfaces a "Late" pill when ``row.late_minutes`` exceeds
    # this many store-local minutes.  Default 5 matches the
    # column default.
    late_threshold_minutes: int = 5


# ── Admin CRUD ──────────────────────────────────────────────


class AdminCreateEntryRequest(BaseModel):
    """Admin-side back-fill payload. Picks the roster member,
    sets the clock-in time, optionally the clock-out time
    (skip for an open / in-progress entry the admin will close
    later) and an explanatory note.

    Timestamps are ISO-8601 strings the SPA writes from a
    ``<input type=datetime-local>`` — server parses them as
    UTC ``datetime`` objects to match the normal punch path.
    """

    model_config = ConfigDict(extra="forbid")

    store_employee_id: int = Field(..., ge=1)
    clock_in_at:       str = Field(..., min_length=1, max_length=40)
    clock_out_at:      str | None = Field(None, max_length=40)
    notes:             str = Field("", max_length=500)


class AdminUpdateEntryRequest(BaseModel):
    """Admin-side edit. Every field is optional — a partial
    PUT leaves omitted fields alone. ``clock_out_at`` may be
    explicitly set to None (use ``clock_out_at: null`` in JSON)
    to re-open a closed shift; the server distinguishes
    "not in payload" from "set to null" via ``model_fields_set``.

    Notes is replace-not-append (it's an admin override —
    cashier-supplied notes survive only when the admin leaves
    the field out of the patch)."""

    model_config = ConfigDict(extra="forbid")

    clock_in_at:  str | None = Field(None, max_length=40)
    clock_out_at: str | None = Field(None, max_length=40)
    notes:        str | None = Field(None, max_length=500)
    status:       TimeClockStatus | None = None


class TimeClockHistoryRow(BaseModel):
    """One audit-log row for a time-clock entry. Returned in
    reverse-chronological order so the most recent change
    surfaces first in the SPA panel."""

    model_config = ConfigDict(extra="forbid")

    id:        int
    at:        str   # ISO-8601 UTC
    actor:     str   # user_name from the audit row
    actor_role: str
    action:    str   # clock_in | clock_out | admin_create | admin_update | admin_delete
    summary:   str


class TimeClockHistoryResponse(BaseModel):
    """The audit chain for one entry — wired to
    ``GET /admin/timeclock/{id}/history``."""

    model_config = ConfigDict(extra="forbid")

    rows: list[TimeClockHistoryRow]


# ── Roster passkey credentials ──────────────────────────────


class TimeClockCredentialRow(BaseModel):
    """One row per roster member's registered passkey, shown
    on the admin credentials page. ``has_passkey=False`` rows
    are included so the admin sees who still needs to enroll."""

    model_config = ConfigDict(extra="forbid")

    store_employee_id: int
    employee_name:     str
    has_passkey:       bool
    name:              str = ""   # display label admin assigned
    registered_at:     str = ""
    last_used_at:      str = ""


class TimeClockCredentialList(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rows: list[TimeClockCredentialRow]


class PunchChallengeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    store_employee_id: int = Field(..., ge=1)


class PunchChallengeResponse(BaseModel):
    """``options_json`` is the WebAuthn assertion options the
    browser passes to ``navigator.credentials.get()``;
    ``assert_token`` is the short-lived JWT the SPA echoes back
    on the clock-in / clock-out call so the server can verify
    against the same challenge."""

    model_config = ConfigDict(extra="forbid")

    options_json: str
    assert_token: str


# ── Paystub ─────────────────────────────────────────────────


class PaystubShiftRow(BaseModel):
    """One shift line on the printable paystub. Mirrors the
    Time-clock entry shape but tightened so the print view
    doesn't have to defend against nulls."""

    model_config = ConfigDict(extra="forbid")

    id:            int
    clock_in_at:   str
    clock_out_at:  str | None = None
    hours_worked:  float | None = None
    status:        TimeClockStatus = "pending"
    notes:         str = ""


class PaystubResponse(BaseModel):
    """Pay summary for one roster member over a date range.

    ``approved_hours × hourly_rate = gross_pay``. Pending /
    rejected shifts are listed alongside but don't count
    toward gross pay — the admin approves them on the payroll
    page first.
    """

    model_config = ConfigDict(extra="forbid")

    store_employee_id: int
    employee_name:     str
    hourly_rate:       float
    approved_hours:    float
    gross_pay:         float
    from_date:         str           # YYYY-MM-DD
    to_date:           str           # YYYY-MM-DD (half-open)
    shifts:            list[PaystubShiftRow]


# ── Break tracking ──────────────────────────────────────────


class BreakPunchRequest(BaseModel):
    """Body for ``/timeclock/break/start`` and
    ``/timeclock/break/stop`` — just identifies which roster
    member is taking / ending the break."""
    model_config = ConfigDict(extra="forbid")

    store_employee_id: int = Field(..., ge=1)


# ── Shift scheduling ───────────────────────────────────────


class ShiftCreateRequest(BaseModel):
    """Body for ``POST /api/v2/admin/timeclock/shifts`` —
    admin schedules a planned shift for a roster member.
    All times are **store-local** (Date + Time), matching how
    operators think about schedules.
    """
    model_config = ConfigDict(extra="forbid")

    store_employee_id: int = Field(..., ge=1)
    shift_date:        _date
    start_time:        _time
    end_time:          _time
    notes:             str = Field("", max_length=500)


class ShiftUpdateRequest(BaseModel):
    """Partial-update payload for
    ``PATCH /api/v2/admin/timeclock/shifts/{id}``.  Every field
    is optional; omitted fields keep their existing value."""
    model_config = ConfigDict(extra="forbid")

    store_employee_id: int | None = Field(None, ge=1)
    shift_date:        _date | None = None
    start_time:        _time | None = None
    end_time:          _time | None = None
    notes:             str | None = Field(None, max_length=500)


class ShiftRow(BaseModel):
    id:                int
    store_employee_id: int
    employee_name:     str
    shift_date:        _date
    start_time:        _time
    end_time:          _time
    notes:             str


class ShiftList(BaseModel):
    rows: list[ShiftRow]
