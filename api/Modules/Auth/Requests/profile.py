"""Account profile schemas — personal info that hangs off the User
row (full_name, email, phone, timezone) plus read-only metadata
(role, last_login_at) the SPA renders alongside.
"""
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


# Allowed values for ``User.theme_preference``. Dark is the
# design-system default — light is opt-in for users who asked for
# it back after the dark+neon redesign. Any other value falls
# through to "dark" at render time (defensive — a partial
# migration or manual DB edit can't leave a user with an unstyled
# page).
ThemePreference = Literal["dark", "light"]


class ProfileResponse(BaseModel):
    """Full payload for the /app/account/profile page on first
    paint. Includes editable fields, read-only metadata, and the
    canonical timezone list so the SPA doesn't have to ship its
    own copy."""

    model_config = ConfigDict(extra="forbid")

    user_id:           int
    username:          str
    role:              str
    full_name:         str
    email:             str
    phone:             str
    timezone:          str
    theme_preference:  ThemePreference
    created_at:        str
    last_login_at:     str
    timezone_choices:  list[str]


class ProfileUpdateRequest(BaseModel):
    """PUT body. Every field is individually optional — the SPA
    may submit only the dirty ones. Validation lives in the
    Service so a future second caller can share the rules."""

    model_config = ConfigDict(extra="forbid")

    full_name:        Optional[str] = Field(default=None, max_length=120)
    email:            Optional[str] = Field(default=None, max_length=255)
    phone:            Optional[str] = Field(default=None, max_length=40)
    timezone:         Optional[str] = Field(default=None, max_length=64)
    theme_preference: Optional[ThemePreference] = None
