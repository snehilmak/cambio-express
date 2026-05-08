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


__all__ = [
    "SuperadminStoreListResponse",
    "SuperadminStoreRow",
]
