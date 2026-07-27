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
    # Targeting. Empty `target_store_ids` = global (every store sees
    # it); a non-empty list scopes the banner + broadcast to those
    # stores only. `target_store_names` is the parallel display list
    # (same order) so the SPA can show "Acme, Bodega #2" without a
    # second fetch.
    target_store_ids: list[int]
    target_store_names: list[str]


class AnnouncementListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rows: list[AnnouncementRow]
    total: int


class AnnouncementCreateRequest(BaseModel):
    """POST body for /announcements. Mirrors the legacy
    /superadmin/announcements/new form fields. `expires_days=0` (or
    omitted) means no expiry — the banner stays up until the
    superadmin disables it. `broadcast=True` queues the message for
    the broadcast-email fan-out (only on create, never on edit).

    `start_at_iso` is the optional ISO-8601 datetime (UTC) when the
    banner should become visible — omit / empty means "start now".
    Honored by `Announcement.visibility.active_announcements`, which
    already skips not-yet-started rows."""
    model_config = ConfigDict(extra="forbid")

    message: str = Field(..., min_length=1, max_length=2000)
    level: str = Field("info", pattern="^(info|warning|error|success)$")
    expires_days: int = Field(0, ge=0, le=365)
    broadcast: bool = False
    start_at_iso: str = Field(
        "",
        description=(
            "ISO-8601 UTC datetime when the banner should go live. "
            "Empty = start immediately."
        ),
    )
    target_store_ids: list[int] = Field(
        default_factory=list,
        description=(
            "Store IDs to scope this announcement to. Empty (the "
            "default) = global — every store sees it and every "
            "opted-in user is emailed. A non-empty list restricts "
            "both the banner and the broadcast to those stores."
        ),
    )


class AnnouncementToggleRequest(BaseModel):
    """POST body for /announcements/{id}/toggle. Explicit
    `is_active` so callers don't accidentally flip the wrong way
    when the cached row is stale."""
    model_config = ConfigDict(extra="forbid")

    is_active: bool


class AnnouncementResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    announcement: AnnouncementRow


class ActiveAnnouncementRow(BaseModel):
    """Slim shape returned to the SPA banner — only the fields the
    banner needs to render. Skips audit/lifecycle fields so a
    cashier's network tab never reveals `created_by`, schedule
    timestamps, or broadcast state for an internal announcement."""
    model_config = ConfigDict(extra="forbid")

    id: int
    message: str
    level: str


class ActiveAnnouncementsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rows: list[ActiveAnnouncementRow]


__all__ = [
    "ActiveAnnouncementRow",
    "ActiveAnnouncementsResponse",
    "AnnouncementCreateRequest",
    "AnnouncementListResponse",
    "AnnouncementResponse",
    "AnnouncementRow",
    "AnnouncementToggleRequest",
]
