"""Announcements — Pydantic request/response schemas."""
from pydantic import BaseModel, ConfigDict, Field


class AnnouncementRow(BaseModel):
    """One Announcement row. `is_visible` is a derived flag — True
    when the row is_active AND inside its starts_at/expires_at window
    — so the SPA doesn't have to recompute the date math client-side."""
    model_config = ConfigDict(extra="forbid")

    id: int
    message: str
    level: str
    is_active: bool
    is_visible: bool
    starts_at: str
    expires_at: str
    created_at: str
    created_by: int | None
    broadcast_requested: bool
    broadcast_sent_at: str


class AnnouncementListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rows: list[AnnouncementRow]
    total: int


class AnnouncementCreateRequest(BaseModel):
    """POST body for /announcements. Mirrors the legacy
    /superadmin/announcements/new form fields. `expires_days=0` (or
    omitted) means no expiry — the banner stays up until the
    superadmin disables it. `broadcast=True` queues the message for
    the broadcast-email fan-out (only on create, never on edit)."""
    model_config = ConfigDict(extra="forbid")

    message: str = Field(..., min_length=1, max_length=2000)
    level: str = Field("info", pattern="^(info|warning|error|success)$")
    expires_days: int = Field(0, ge=0, le=365)
    broadcast: bool = False


class AnnouncementToggleRequest(BaseModel):
    """POST body for /announcements/{id}/toggle. Explicit
    `is_active` so callers don't accidentally flip the wrong way
    when the cached row is stale."""
    model_config = ConfigDict(extra="forbid")

    is_active: bool


class AnnouncementResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    announcement: AnnouncementRow


__all__ = [
    "AnnouncementCreateRequest",
    "AnnouncementListResponse",
    "AnnouncementResponse",
    "AnnouncementRow",
    "AnnouncementToggleRequest",
]
