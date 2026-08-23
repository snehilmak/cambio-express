"""PosImport — Request/response schemas.

Money crosses the API as dollars floats (the app-wide contract).
Uploads are base64 in the JSON body (the ReportImport precedent):
one PJR XML file or a ZIP of many.
"""
from pydantic import BaseModel, ConfigDict, Field


class NaxmlUploadRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content_base64: str = Field(..., min_length=1)


class NaxmlCommitRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content_base64: str = Field(..., min_length=1)
    day: str = Field(..., min_length=10, max_length=10)  # YYYY-MM-DD


class FuelGradeRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    grade_id: str
    description: str
    gallons: float
    amount: float


class ImportDepartmentRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    merchandise_code: str
    amount: float
    department_id: int | None   # mapped target, if any
    department_name: str


class ImportRegisterRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    business_date: str
    register_label: str
    net_sales: float
    sales_tax: float
    refunds: float
    cash_total: float
    card_total: float
    other_total: float
    sale_count: int
    refund_count: int
    opening_cash: float | None
    departments: list[ImportDepartmentRow]
    fuel: list[FuelGradeRow]


class NaxmlPreviewResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    file_count: int
    event_count: int
    parse_errors: list[str]
    business_dates: list[str]
    registers: list[ImportRegisterRow]
    unmapped_codes: list[str]


class MappingRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    merchandise_code: str
    department_id: int
    department_name: str


class MappingListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mappings: list[MappingRow]


class MappingWriteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mappings: list["MappingWriteRow"] = Field(..., max_length=500)


class MappingWriteRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    merchandise_code: str = Field(..., min_length=1, max_length=20)
    department_id: int = Field(..., ge=1)


class NaxmlCommitResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    day: str
    closes_written: int
    registers: list[str]
