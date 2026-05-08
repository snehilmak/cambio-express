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


__all__ = [
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
