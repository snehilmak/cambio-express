"""Account notifications schemas — boolean preference toggles
that hang off the User row.
"""
from typing import Optional

from pydantic import BaseModel, ConfigDict


class NotificationsResponse(BaseModel):
    """Per-user notification preferences. `trial_toggle_applies`
    tells the SPA whether to render the Trial-ending toggle as
    interactive (True) or grey/informational (False — already
    paid, or role doesn't own a trial)."""

    model_config = ConfigDict(extra="forbid")

    notify_trial_reminders:    bool
    notify_announcement_email: bool
    trial_toggle_applies:      bool
    role:                      str


class NotificationsUpdateRequest(BaseModel):
    """PUT body. Both fields optional — None = don't touch.
    Empty payload is a no-op (HTTP 200 with current state)."""

    model_config = ConfigDict(extra="forbid")

    notify_trial_reminders:    Optional[bool] = None
    notify_announcement_email: Optional[bool] = None
