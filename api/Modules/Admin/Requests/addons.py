"""Pydantic schemas for the subscription add-on endpoints."""
from pydantic import BaseModel, ConfigDict


class AddonRow(BaseModel):
    """One subscription add-on row, with its activation status for
    the calling store. Mirrors the legacy ADDONS_CATALOG entry +
    a derived `is_active` from the store's CSV addon list."""
    model_config = ConfigDict(extra="forbid")

    key: str
    name: str
    price_label: str
    tagline: str
    status: str
    is_active: bool


class AddonListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rows: list[AddonRow]
    total: int
    has_paid_plan: bool


class AddonToggleResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    addon: AddonRow
