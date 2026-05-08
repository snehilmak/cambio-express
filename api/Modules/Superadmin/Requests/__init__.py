"""Superadmin — Pydantic request/response schemas."""
from pydantic import BaseModel, ConfigDict

from api.Modules.Superadmin.Requests.discounts import (
    DiscountCodeListResponse,
    DiscountCodeResponse,
    DiscountCodeRow,
    DiscountCodeToggleRequest,
)


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


class SuperadminAnomalyRow(BaseModel):
    """One platform anomaly row. `kind` is one of
    `quiet_store` / `big_over_short`; `severity` is
    `low` / `medium` / `high`. `description` is the human-readable
    explanation the SPA renders verbatim. `href` is the legacy
    drill-down URL — once those pages migrate it'll point to
    /app/* equivalents."""
    model_config = ConfigDict(extra="forbid")

    kind: str
    severity: str
    store_id: int
    store_name: str
    store_slug: str
    description: str
    href: str


class SuperadminAnomalyListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rows: list[SuperadminAnomalyRow]
    total: int


__all__ = [
    "DiscountCodeListResponse",
    "DiscountCodeResponse",
    "DiscountCodeRow",
    "DiscountCodeToggleRequest",
    "SuperadminAnomalyListResponse",
    "SuperadminAnomalyRow",
    "SuperadminAuditListResponse",
    "SuperadminAuditRow",
    "SuperadminStoreListResponse",
    "SuperadminStoreRow",
]
