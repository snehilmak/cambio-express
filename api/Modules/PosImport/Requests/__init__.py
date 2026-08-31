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


# ── Site agent (Phase B) ───────────────────────────────────


class AgentUploadRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    filename:       str = Field(..., min_length=1, max_length=120)
    content_base64: str = Field(..., min_length=1)


class AgentUploadResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    staged: bool
    duplicate: bool
    business_date: str | None
    parse_error: str


class AgentKeyIssueRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str = Field("", max_length=80)


class AgentKeyIssueResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    label: str
    # The raw key — returned exactly once, never retrievable again.
    key: str


class AgentKeyRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    label: str
    created_at: str
    last_used_at: str | None
    revoked: bool


class AgentKeyListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    keys: list[AgentKeyRow]


class StagedDayRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    business_date: str
    file_count: int
    error_count: int
    committed: bool


class StagedDaysResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    days: list[StagedDayRow]


class StagedCommitRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    day: str = Field(..., min_length=10, max_length=10)


class PriceBookHarvestRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pos_code: str
    pos_code_format: str
    description: str
    merchandise_code: str
    department_id: int | None
    department_name: str
    price: float
    last_seen: str
    seen_count: int
    already_in_price_book: bool


class PriceBookHarvestResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[PriceBookHarvestRow]
    new_count: int
    existing_count: int


class PriceBookSeedResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    created: int
    skipped_existing: int


class ItemMovementRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pos_code: str
    description: str
    merchandise_code: str
    quantity: float
    amount: float
    avg_price: float
    in_price_book: bool


class ItemMovementResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rows: list[ItemMovementRow]
    total: int
    page: int
    total_pages: int
    start: str
    end: str
    total_quantity: float
    total_amount: float


# ── Transactions (G-6) ──────────────────────────────────────
#
# The register's own ticket detail, so an operator can answer "what
# sold on this transaction?" and "which tickets had a voided item?".
# Cancelled lines are RETURNED, flagged by `status`, because a
# voided item is exactly what a manager is looking for — the money
# fields on the parent event already exclude them.


class PosTransactionRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    business_date: str
    kind: str
    register_id: str
    cashier_id: str
    transaction_no: str
    receipt_at: str | None
    item_count: int
    gross: float
    tax: float
    grand_total: float
    has_voided_line: bool
    training_mode: bool
    offline: bool
    suspended: bool


class PosTransactionLineRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    line_seq: int
    status: str
    pos_code: str
    description: str
    entry_method: str
    merchandise_code: str
    quantity: float
    amount: float
    actual_price: float
    regular_price: float
    is_fuel: bool
    fuel_grade_id: str
    fuel_position: str
    gallons: float


class PosTransactionTenderRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    sub_code: str
    amount: float
    is_change: bool
    status: str


class PosTransactionDetail(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    business_date: str
    source_file: str
    kind: str
    register_id: str
    cashier_id: str
    till_id: str
    transaction_no: str
    event_sequence_id: str
    started_at: str | None
    ended_at: str | None
    receipt_at: str | None
    outside: bool
    training_mode: bool
    offline: bool
    suspended: bool
    gross: float
    net: float
    tax: float
    grand_total: float
    has_voided_line: bool
    lines: list[PosTransactionLineRow]
    tenders: list[PosTransactionTenderRow]


class PosTransactionListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rows: list[PosTransactionRow]
    total: int
    page: int
    total_pages: int
    # Totals for the WHOLE filtered set, not just this page — a
    # per-page sum would silently disagree with the row count above
    # it and read as a bug.
    total_grand: float
    voided_count: int


class PosTransactionDetailResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    transaction: PosTransactionDetail
