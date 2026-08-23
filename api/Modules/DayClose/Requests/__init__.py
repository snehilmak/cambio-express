"""DayClose — Request/response schemas.

Money crosses the API as dollars floats (the app-wide contract);
cents stay in the DB + Services (P0-3 convention). ``cash_counted``
is nullable end-to-end: null means "drawer not counted", which is
different from a counted $0.00.
"""
from pydantic import BaseModel, ConfigDict, Field


class DepartmentWriteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name:       str = Field(..., min_length=1, max_length=80)
    sort_order: int = Field(0, ge=0, le=10000)


class DepartmentUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name:       str | None = Field(None, min_length=1, max_length=80)
    sort_order: int | None = Field(None, ge=0, le=10000)
    is_active:  bool | None = None


class DepartmentRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    name: str
    sort_order: int
    is_active: bool


class DepartmentListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    departments: list[DepartmentRow]


class DepartmentResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    department: DepartmentRow


class DepartmentSaleLine(BaseModel):
    model_config = ConfigDict(extra="forbid")

    department_id: int = Field(..., ge=1)
    amount:        float = Field(..., ge=0)


class RegisterCloseWriteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    register_label: str = Field(..., min_length=1, max_length=40)
    shift_label:    str = Field("", max_length=40)
    gross_sales:    float = Field(..., ge=0)
    sales_tax:      float = Field(0, ge=0)
    cash_total:     float = Field(0, ge=0)
    card_total:     float = Field(0, ge=0)
    other_total:    float = Field(0, ge=0)
    cash_counted:   float | None = Field(None, ge=0)
    notes:          str = Field("", max_length=500)
    department_sales: list[DepartmentSaleLine] = Field(
        default_factory=list, max_length=200,
    )


class DepartmentSaleRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    department_id: int
    department_name: str
    amount: float


class RegisterCloseRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    register_label: str
    shift_label: str
    gross_sales: float
    sales_tax: float
    cash_total: float
    card_total: float
    other_total: float
    cash_counted: float | None
    over_short: float | None
    tender_variance: float
    notes: str
    source: str
    department_sales: list[DepartmentSaleRow]


class DepartmentTotalRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    department_id: int
    department_name: str
    amount: float


class DayCloseSummaryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    date: str
    closes: list[RegisterCloseRow]
    department_totals: list[DepartmentTotalRow]
    gross_sales: float
    sales_tax: float
    cash_total: float
    card_total: float
    other_total: float
    over_short: float | None
    tender_variance: float
    uncounted_drawers: int
