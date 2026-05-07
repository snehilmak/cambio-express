"""Pydantic schemas for the admin store-info endpoints."""
from pydantic import BaseModel, ConfigDict, Field


class StoreInfoRow(BaseModel):
    """Read shape — fields the SPA's settings page renders.
    Slug / plan / billing fields are read-only here; the
    superadmin owns those."""

    model_config = ConfigDict(extra="forbid")

    id: int
    name: str
    slug: str
    email: str = ""
    phone: str = ""
    address: str = ""
    plan: str = "trial"
    federal_tax_rate: float = 0.01
    is_active: bool = True


class StoreInfoResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    store: StoreInfoRow


class StoreInfoUpdateRequest(BaseModel):
    """PUT body. Only the operator-editable fields. Slug,
    plan, billing, retention etc. stay server-managed."""

    model_config = ConfigDict(extra="forbid")

    name:             str | None = Field(None, max_length=120)
    email:            str | None = Field(None, max_length=120)
    phone:            str | None = Field(None, max_length=40)
    address:          str | None = Field(None, max_length=255)
    federal_tax_rate: float | None = Field(None, ge=0, le=1)
