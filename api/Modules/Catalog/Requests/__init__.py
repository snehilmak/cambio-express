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
    # Item-editor parity (P2-5): vendor ordering number, size
    # label, case pack fields, EBT eligibility.
    item_number:     str = Field("", max_length=40)
    size:            str = Field("", max_length=40)
    case_size:       int | None = Field(None, ge=1)
    case_cost:       float | None = Field(None, ge=0)
    is_ebt:          bool = False


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
    item_number:     str | None = Field(None, max_length=40)
    size:            str | None = Field(None, max_length=40)
    # 0 clears case_size / case_cost (None = leave unchanged),
    # mirroring the FK-clear sentinel above.
    case_size:       int | None = Field(None, ge=0)
    case_cost:       float | None = Field(None, ge=0)
    is_ebt:          bool | None = None


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
    item_number: str
    size: str
    case_size: int | None
    case_cost: float | None
    is_ebt: bool


class ItemResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item: ItemRow


class ItemListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rows: list[ItemRow]
    total: int
    page: int
    total_pages: int


# ── Purchase invoices ──────────────────────────────────────


class InvoiceLineWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item_id:     int | None = Field(None, ge=1)
    description: str = Field("", max_length=160)
    quantity:    float = Field(1, gt=0)
    unit_cost:   float = Field(0, ge=0)
    # The printed extended amount — omit to derive quantity × cost.
    line_total:  float | None = Field(None, ge=0)


class InvoiceWriteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    vendor_id:      int = Field(..., ge=1)
    invoice_number: str = Field(..., min_length=1, max_length=60)
    invoice_date:   str = Field(..., min_length=10, max_length=10)
    due_date:       str | None = Field(None, min_length=10, max_length=10)
    subtotal:       float = Field(0, ge=0)
    tax:            float = Field(0, ge=0)
    other:          float = Field(0, ge=0)
    status:         str = Field("open", pattern="^(open|paid)$")
    paid_on:        str | None = Field(None, min_length=10, max_length=10)
    notes:          str = Field("", max_length=500)
    lines:          list[InvoiceLineWrite] = Field(
        default_factory=list, max_length=200,
    )
    # Push each linked line's unit cost onto its price-book item.
    update_item_costs: bool = False


class InvoiceUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    vendor_id:      int | None = Field(None, ge=1)
    invoice_number: str | None = Field(None, min_length=1, max_length=60)
    invoice_date:   str | None = Field(None, min_length=10, max_length=10)
    due_date:       str | None = Field(None, min_length=10, max_length=10)
    clear_due_date: bool = False
    subtotal:       float | None = Field(None, ge=0)
    tax:            float | None = Field(None, ge=0)
    other:          float | None = Field(None, ge=0)
    status:         str | None = Field(None, pattern="^(open|paid)$")
    paid_on:        str | None = Field(None, min_length=10, max_length=10)
    notes:          str | None = Field(None, max_length=500)
    # Present = replace the full line set; absent = leave lines alone.
    lines:          list[InvoiceLineWrite] | None = Field(
        None, max_length=200,
    )
    update_item_costs: bool = False


class InvoiceLineRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    item_id: int | None
    item_name: str
    description: str
    quantity: float
    unit_cost: float
    line_total: float


class InvoiceRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    vendor_id: int
    vendor_name: str
    invoice_number: str
    invoice_date: str
    due_date: str | None
    subtotal: float
    tax: float
    other: float
    total: float
    status: str
    paid_on: str | None
    notes: str
    line_count: int


class InvoiceDetail(InvoiceRow):
    lines: list[InvoiceLineRow]


class InvoiceResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    invoice: InvoiceDetail
    # How many price-book items had their cost updated by this
    # write (0 unless update_item_costs was set).
    items_cost_updated: int


class InvoiceListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rows: list[InvoiceRow]
    total: int
    page: int
    total_pages: int
