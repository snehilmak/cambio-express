"""Account notifications schemas — boolean preference toggles
that hang off the User row.
"""
from typing import Optional

from pydantic import BaseModel, ConfigDict


class NotificationsResponse(BaseModel):
    """Per-user notification preferences.

    Three ``*_applies`` flags tell the SPA when a toggle is
    interactive vs. greyed-out informational:

      * ``trial_toggle_applies`` — True only for admins / owners
        of a store currently in active / expiring-soon / grace
        trial state.
      * ``locked_day_digest_applies`` — True only for admins /
        owners (employees don't receive the digest by design).
      * ``daily_summary_applies`` — same as the locked-day digest:
        admins / owners only.
    """

    model_config = ConfigDict(extra="forbid")

    notify_trial_reminders:        bool
    notify_announcement_email:     bool
    notify_locked_day_digest:      bool
    notify_daily_summary:          bool
    trial_toggle_applies:          bool
    locked_day_digest_applies:     bool
    daily_summary_applies:         bool
    role:                          str


class NotificationsUpdateRequest(BaseModel):
    """PUT body. Every field optional — None = don't touch.
    Empty payload is a no-op (HTTP 200 with current state)."""

    model_config = ConfigDict(extra="forbid")

    notify_trial_reminders:    Optional[bool] = None
    notify_announcement_email: Optional[bool] = None
    notify_locked_day_digest:  Optional[bool] = None
    notify_daily_summary:      Optional[bool] = None
