"""Superadmin — Pydantic request/response schemas."""
from pydantic import BaseModel, ConfigDict, Field

from api.Modules.Superadmin.Requests.discounts import (
    DiscountCodeListResponse,
    DiscountCodeResponse,
    DiscountCodeRow,
    DiscountCodeToggleRequest,
)
from api.Modules.Superadmin.Requests.stores import (
    SuperadminOwnerLinkCreateRequest,
    SuperadminOwnerLinkListResponse,
    SuperadminOwnerLinkRow,
    SuperadminStoreCreateRequest,
    SuperadminStoreCreditRequest,
    SuperadminStoreCreditResponse,
    SuperadminStoreDetailResponse,
    SuperadminStoreDetailRow,
    SuperadminStoreFreezeRequest,
    SuperadminStoreFreezeResponse,
    SuperadminStoreUpdateRequest,
)


class PlatformUserCreateRequest(BaseModel):
    """POST /superadmin/platform-users — create a store-less
    platform login. v1 mints only the tickets-only ``support``
    role; the role is fixed server-side, not caller-supplied."""
    model_config = ConfigDict(extra="forbid")

    username: str = Field(..., min_length=3, max_length=80)
    full_name: str = Field("", max_length=120)
    email: str = Field("", max_length=255)
    password: str = Field(..., min_length=8, max_length=200)


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


class SuperadminReportRow(BaseModel):
    """One report card on the report-center index. `url` is the
    Flask drilldown path (still on Flask until each report
    individually migrates); `status` is `ready` when an endpoint
    backs the report or `coming_soon` when only a placeholder is
    declared. The SPA renders the `View` button on `ready` rows
    and a disabled `Coming soon` pill on the rest."""
    model_config = ConfigDict(extra="forbid")

    key: str
    label: str
    description: str
    url: str | None
    status: str


class SuperadminReportCategory(BaseModel):
    """Group of related reports — Platform Health / Revenue /
    Stripe / Trial Funnel / Feature Adoption / Support. The
    `icon` is an inline stroke SVG matching the rest of the
    sidebar/nav iconography (CLAUDE.md design system)."""
    model_config = ConfigDict(extra="forbid")

    key: str
    label: str
    icon: str
    reports: list[SuperadminReportRow]


class SuperadminReportListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    categories: list[SuperadminReportCategory]


__all__ = [
    "DiscountCodeListResponse",
    "DiscountCodeResponse",
    "DiscountCodeRow",
    "DiscountCodeToggleRequest",
    "SuperadminAnomalyListResponse",
    "SuperadminAnomalyRow",
    "SuperadminAuditListResponse",
    "SuperadminAuditRow",
    "SuperadminReportCategory",
    "SuperadminReportListResponse",
    "SuperadminReportRow",
    "SuperadminOwnerLinkCreateRequest",
    "SuperadminOwnerLinkListResponse",
    "SuperadminOwnerLinkRow",
    "SuperadminStoreCreateRequest",
    "SuperadminStoreCreditRequest",
    "SuperadminStoreCreditResponse",
    "SuperadminStoreDetailResponse",
    "SuperadminStoreDetailRow",
    "SuperadminStoreFreezeRequest",
    "SuperadminStoreFreezeResponse",
    "SuperadminStoreListResponse",
    "SuperadminStoreRow",
    "SuperadminStoreUpdateRequest",
]
