"""Owners — Pydantic request/response schemas."""
from pydantic import BaseModel, ConfigDict


class OwnerStoreRow(BaseModel):
    """One store in the owner's umbrella, decorated with period-scoped
    operational stats (transfers / volume / over-short) and the
    company mix that drove that volume."""
    model_config = ConfigDict(extra="forbid")

    store_id: int
    store_name: str
    store_slug: str
    transfer_count: int
    volume: float
    over_short: float
    report_count: int
    companies: list["OwnerStoreCompanyChip"]


class OwnerStoreCompanyChip(BaseModel):
    model_config = ConfigDict(extra="forbid")

    company: str
    count: int
    volume: float


class OwnerLocationsResponse(BaseModel):
    """Per-store rows for /api/v2/owner/locations.

    `total` is the unfiltered umbrella size (so the SPA can
    distinguish "owner has no stores connected yet" from "search
    returned zero matches").
    """
    model_config = ConfigDict(extra="forbid")

    rows: list[OwnerStoreRow]
    total: int
    matched: int


OwnerStoreRow.model_rebuild()


class OwnerPLRollupRow(BaseModel):
    """One store's monthly P&L row for /owner/pl-rollup. `has_pl` is
    False when there's no MonthlyFinancial row for the (store, year,
    month) yet — UI can render a "—" placeholder instead of $0.00."""
    model_config = ConfigDict(extra="forbid")

    store_id: int
    store_name: str
    store_slug: str
    has_pl: bool
    revenue: float
    purchases: float
    expenses: float
    over_short: float
    net: float


class OwnerPLRollupTotals(BaseModel):
    model_config = ConfigDict(extra="forbid")

    revenue: float
    purchases: float
    expenses: float
    over_short: float
    net: float


class OwnerPLRollupResponse(BaseModel):
    """Side-by-side monthly P&L for every store in the owner umbrella.
    Sorted by net income desc — strongest performers first. `year` /
    `month` echo back so the SPA's pager knows what to navigate from.
    `year_choices` is the set of years with at least one P&L row across
    the umbrella, used to render a year-dropdown without an extra
    request."""
    model_config = ConfigDict(extra="forbid")

    year: int
    month: int
    rows: list[OwnerPLRollupRow]
    totals: OwnerPLRollupTotals
    year_choices: list[int]


class OwnerBillingRow(BaseModel):
    """One store's subscription state on the owner billing page.

    `monthly_cost` normalises yearly plans to a monthly figure so
    stores on different cadences can be summed. `attention` is a slug
    ("" | "trial_ending" | "trial_expired" | "inactive" |
    "retention") the SPA maps to wording + a pill tone."""
    model_config = ConfigDict(extra="forbid")

    store_id: int
    store_name: str
    store_slug: str
    plan: str
    plan_label: str
    plan_price_label: str
    billing_cycle: str
    monthly_cost: float
    trial_status: str
    trial_days_left: int | None
    trial_ends_at: str | None
    retention_days_left: int | None
    addon_count: int
    addon_monthly_cost: float
    has_paid_plan: bool
    attention: str


class OwnerBillingTotals(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stores: int
    paid_stores: int
    trial_stores: int
    inactive_stores: int
    monthly_cost: float
    addon_monthly_cost: float
    attention_count: int


class OwnerBillingResponse(BaseModel):
    """Subscription state for every store in the umbrella, stores
    needing action first, then alphabetical."""
    model_config = ConfigDict(extra="forbid")

    rows: list[OwnerBillingRow]
    totals: OwnerBillingTotals


__all__ = [
    "OwnerBillingResponse",
    "OwnerBillingRow",
    "OwnerBillingTotals",
    "OwnerConnectCodeListResponse",
    "OwnerConnectCodeResponse",
    "OwnerConnectCodeRow",
    "OwnerLocationsResponse",
    "OwnerPLRollupResponse",
    "OwnerPLRollupRow",
    "OwnerPLRollupTotals",
    "OwnerStoreCompanyChip",
    "OwnerStoreRow",
    "OwnerUnlinkRequest",
]


class OwnerConnectCodeRow(BaseModel):
    """One owner-generated connect code (the 8-char invite a store
    admin redeems on /admin/settings to link their store)."""
    model_config = ConfigDict(extra="forbid")

    id: int
    code: str
    created_at: str
    expires_at: str
    used_at: str
    used_by_store_name: str
    revoked_at: str
    is_redeemed: bool
    is_revoked: bool
    is_expired: bool


class OwnerConnectCodeListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rows: list[OwnerConnectCodeRow]
    total: int


class OwnerConnectCodeResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: OwnerConnectCodeRow


class OwnerUnlinkRequest(BaseModel):
    """POST body for /owner/unlink/{store_id}. Empty schema today
    (the store_id is in the path), but `extra="forbid"` keeps it
    explicit + future-extensible."""
    model_config = ConfigDict(extra="forbid")


from typing import Literal

from pydantic import Field


class OwnerBulkAddUserRequest(BaseModel):
    """POST body for ``/owner/bulk-add-user``. Creates the same
    login at every store in ``store_ids`` that's actually in the
    owner's umbrella. Stores outside the umbrella are reported as
    ``rejected`` rather than 403'd so the operator sees the full
    result table.

    The person is identified by email and/or phone (L-2) — at
    least one is required."""
    model_config = ConfigDict(extra="forbid")

    email:     str | None = Field(None, max_length=255)
    phone:     str | None = Field(None, max_length=40)
    password:  str = Field(..., min_length=8, max_length=200)
    full_name: str = Field("", max_length=120)
    role:      Literal["employee"] = "employee"
    store_ids: list[int] = Field(..., min_length=1, max_length=50)


class OwnerBulkAddUserResultRow(BaseModel):
    """One row per requested store_id, ordered same as the
    request payload."""
    model_config = ConfigDict(extra="forbid")

    store_id:   int
    store_name: str = ""
    status:     Literal["created", "skipped", "rejected"]
    detail:     str = ""


class OwnerBulkAddUserResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    created:  int
    skipped:  int
    rejected: int
    results:  list[OwnerBulkAddUserResultRow]


# ── Cross-store defaults ────────────────────────────────────


from api.Modules.Admin.Requests.store_info import StoreHourEntry


class OwnerCrossStoreDefaultsRequest(BaseModel):
    """POST body for ``/owner/cross-store-defaults``. Every
    field is optional — the operator picks which ones to push.
    Validation mirrors the per-store
    ``Admin.Requests.store_info.StoreInfoUpdateRequest`` since
    each store's update goes through the same service guard."""

    model_config = ConfigDict(extra="forbid")

    store_ids: list[int] = Field(..., min_length=1, max_length=50)

    federal_tax_rate:          float | None = Field(None, ge=0, le=1)
    timezone:                  str   | None = Field(None, max_length=60)
    store_hours:               list[StoreHourEntry] | None = None
    enforce_business_hours:    bool  | None = None
    timeclock_require_passkey: bool  | None = None
    phone:                     str   | None = Field(None, max_length=40)
    address:                   str   | None = Field(None, max_length=255)


class OwnerCrossStoreResultRow(BaseModel):
    """One row per requested store_id, ordered same as the
    request payload."""
    model_config = ConfigDict(extra="forbid")

    store_id:   int
    store_name: str = ""
    status:     Literal["updated", "rejected"]
    detail:     str = ""


class OwnerCrossStoreResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    updated:  int
    rejected: int
    results:  list[OwnerCrossStoreResultRow]
