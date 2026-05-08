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


__all__ = [
    "OwnerLocationsResponse",
    "OwnerStoreCompanyChip",
    "OwnerStoreRow",
]
