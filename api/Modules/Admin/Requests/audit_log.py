"""Admin audit-log schemas."""
from pydantic import BaseModel, ConfigDict


class AdminAuditRow(BaseModel):
    """One row in the merged operator audit-log feed.

    `source` is "operator" for OperatorAuditLog rows (transfer
    deletes, batch creates/updates, daily-report locks/unlocks)
    or "transfer" for TransferAudit rows (transfer creates / edits
    / status changes). The legacy Jinja page didn't expose this
    field but it's useful for the SPA's row-key generation."""

    model_config = ConfigDict(extra="forbid")

    ts:           str
    user_name:    str
    user_role:    str
    action:       str
    target_type:  str
    target_id:    str
    target_label: str
    summary:      str
    source:       str


class AdminAuditUserOption(BaseModel):
    """An entry in the user filter dropdown — every User on the
    store sorted by full_name (then username)."""

    model_config = ConfigDict(extra="forbid")

    id:        int
    label:     str
    role:      str


class AdminAuditLogResponse(BaseModel):
    """Page-shaped response. `total` is the count after filters
    are applied; `total_pages` is rounded up against the fixed
    per-page constant so the SPA can render the pager without
    knowing the magic number."""

    model_config = ConfigDict(extra="forbid")

    rows:           list[AdminAuditRow]
    total:          int
    page:           int
    per_page:       int
    total_pages:    int
    store_users:    list[AdminAuditUserOption]
    target_filter:  str
    action_filter:  str
    user_filter:    str
