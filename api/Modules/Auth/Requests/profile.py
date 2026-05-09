"""Account profile schemas — personal info that hangs off the User
row (full_name, email, phone, timezone) plus read-only metadata
(role, last_login_at) the SPA renders alongside.
"""
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


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
    created_at:        str
    last_login_at:     str
    timezone_choices:  list[str]


class ProfileUpdateRequest(BaseModel):
    """PUT body. All four editable fields are individually
    optional — the SPA could submit only the dirty ones — but
    the legacy form always sends all four, so the service layer
    treats absent == 'don't change'.

    Validation lives in the Service so the legacy app._update_user_profile
    helper and the FastAPI path can share rules."""

    model_config = ConfigDict(extra="forbid")

    full_name: Optional[str] = Field(default=None, max_length=120)
    email:     Optional[str] = Field(default=None, max_length=255)
    phone:     Optional[str] = Field(default=None, max_length=40)
    timezone:  Optional[str] = Field(default=None, max_length=64)
