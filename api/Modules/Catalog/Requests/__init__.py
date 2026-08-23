"""Catalog — Request/response schemas.

Money crosses the API as dollars floats (the app-wide contract);
cents stay in the DB + Services (P0-3 convention). Item lists use
the shared pagination envelope (rows/total/page/total_pages) so the
SPA's Pager + live-search hooks work unchanged.
"""
from pydantic import BaseModel, ConfigDict, Field


# ── Vendors ────────────────────────────────────────────────


class VendorWriteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name:           str = Field(..., min_length=1, max_length=120)
    contact_name:   str = Field("", max_length=120)
    phone:          str = Field("", max_length=30)
    email:          str = Field("", max_length=200)
    account_number: str = Field("", max_length=60)
    notes:          str = Field("", max_length=500)


class VendorUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name:           str | None = Field(None, min_length=1, max_length=120)
    contact_name:   str | None = Field(None, max_length=120)
    phone:          str | None = Field(None, max_length=30)
    email:          str | None = Field(None, max_length=200)
    account_number: str | None = Field(None, max_length=60)
    notes:          str | None = Field(None, max_length=500)
    is_active:      bool | None = None


class VendorRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    name: str
    contact_name: str
    phone: str
    email: str
    account_number: str
    notes: str
    is_active: bool
    item_count: int


class VendorListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    vendors: list[VendorRow]


class VendorResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    vendor: VendorRow


# ── Price-book items ───────────────────────────────────────


class ItemWriteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pos_code:        str = Field(..., min_length=1, max_length=30)
    pos_code_format: str = Field("upc", pattern="^(upc|plu)$")
    name:            str = Field(..., min_length=1, max_length=160)
    department_id:   int | None = Field(None, ge=1)
    vendor_id:       int | None = Field(None, ge=1)
    price:           float = Field(0, ge=0)
    cost:            float = Field(0, ge=0)
    is_taxable:      bool = True


class ItemUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pos_code:        str | None = Field(None, min_length=1, max_length=30)
    pos_code_format: str | None = Field(None, pattern="^(upc|plu)$")
    name:            str | None = Field(None, min_length=1, max_length=160)
    # department_id / vendor_id use 0 as an explicit "clear the
    # link" sentinel — None means "leave unchanged" in a PATCH-style
    # update, so 0 is the only way to unset an optional FK.
    department_id:   int | None = Field(None, ge=0)
    vendor_id:       int | None = Field(None, ge=0)
    price:           float | None = Field(None, ge=0)
    cost:            float | None = Field(None, ge=0)
    is_taxable:      bool | None = None
    is_active:       bool | None = None


class ItemRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    pos_code: str
    pos_code_format: str
    name: str
    department_id: int | None
    department_name: str
    vendor_id: int | None
    vendor_name: str
    price: float
    cost: float
    is_taxable: bool
    is_active: bool
    source: str


class ItemResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item: ItemRow


class ItemListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rows: list[ItemRow]
    total: int
    page: int
    total_pages: int
