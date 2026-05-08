"""Superadmin — Pydantic request/response schemas."""
from pydantic import BaseModel, ConfigDict


class SuperadminStoreRow(BaseModel):
    """One store on the platform-wide stores list. Fields chosen to
    cover the legacy `/superadmin/stores` table view: identity,
    plan, trial state, retention timer, and Stripe linkage."""
    model_config = ConfigDict(extra="forbid")

    store_id: int
    name: str
    slug: str
    email: str
    phone: str
    plan: str
    billing_cycle: str
    is_active: bool
    created_at: str
    trial_ends_at: str
    grace_ends_at: str
    data_retention_until: str
    stripe_customer_id: str
    stripe_subscription_id: str


class SuperadminStoreListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rows: list[SuperadminStoreRow]
    total: int


class SuperadminAuditRow(BaseModel):
    """One row from the platform-wide superadmin_audit_log. Snapshot
    fields (admin_name, action, target_type, target_id, details,
    created_at) — enough to render the table without a JOIN."""
    model_config = ConfigDict(extra="forbid")

    id: int
    admin_id: int | None
    admin_name: str
    action: str
    target_type: str
    target_id: str
    details: str
    created_at: str


class SuperadminAuditListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rows: list[SuperadminAuditRow]
    total: int
    page: int
    per_page: int
    total_pages: int


__all__ = [
    "SuperadminAuditListResponse",
    "SuperadminAuditRow",
    "SuperadminStoreListResponse",
    "SuperadminStoreRow",
]
