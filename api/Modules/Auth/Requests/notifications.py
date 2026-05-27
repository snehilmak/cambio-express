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
    # Per-kind push-channel toggles — symmetrical to the email
    # toggles above.  Default-True so flipping the channel on
    # immediately delivers every kind; users opt out per-kind.
    notify_trial_reminders_push:    bool
    notify_announcement_push:       bool
    notify_locked_day_digest_push:  bool
    notify_daily_summary_push:      bool
    notify_high_variance:           bool = False
    notify_high_variance_push:      bool = False
    notify_store_offline:           bool = False
    notify_store_offline_push:      bool = False
    trial_toggle_applies:          bool
    locked_day_digest_applies:     bool
    daily_summary_applies:         bool
    high_variance_applies:         bool = False
    store_offline_applies:         bool = False
    role:                          str


class NotificationsUpdateRequest(BaseModel):
    """PUT body. Every field optional — None = don't touch.
    Empty payload is a no-op (HTTP 200 with current state)."""

    model_config = ConfigDict(extra="forbid")

    notify_trial_reminders:        Optional[bool] = None
    notify_announcement_email:     Optional[bool] = None
    notify_locked_day_digest:      Optional[bool] = None
    notify_daily_summary:          Optional[bool] = None
    notify_trial_reminders_push:   Optional[bool] = None
    notify_announcement_push:      Optional[bool] = None
    notify_locked_day_digest_push: Optional[bool] = None
    notify_daily_summary_push:     Optional[bool] = None
    notify_high_variance:          Optional[bool] = None
    notify_high_variance_push:     Optional[bool] = None
    notify_store_offline:          Optional[bool] = None
    notify_store_offline_push:     Optional[bool] = None
