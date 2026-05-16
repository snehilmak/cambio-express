"""Per-user activity feed schemas.

Backs `GET /api/v2/auth/activity` — every audit row authored by
the current user, across every store they've touched.
"""
from pydantic import BaseModel, ConfigDict


class MyActivityRow(BaseModel):
    """One row in the per-user activity feed.

    Mirrors the admin audit-log row shape but adds `store_name`
    so multi-store cashiers (and owners) can tell which store an
    action was logged at. The `user_name`/`user_role` columns are
    omitted — every row in this feed is the same user, so they'd
    be noise."""

    model_config = ConfigDict(extra="forbid")

    ts:           str
    action:       str
    target_type:  str
    target_id:    str
    target_label: str
    summary:      str
    source:       str
    store_id:     int
    store_name:   str


class MyActivityResponse(BaseModel):
    """Page-shaped response for the activity feed."""

    model_config = ConfigDict(extra="forbid")

    rows:           list[MyActivityRow]
    total:          int
    page:           int
    per_page:       int
    total_pages:    int
    target_filter:  str
    action_filter:  str
