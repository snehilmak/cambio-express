"""Pydantic schemas for the daily-book read-side."""
from pydantic import BaseModel, ConfigDict, Field


class DailyReportRow(BaseModel):
    """One day's roll-up. Pre-computes receipts / disbursements /
    net so the React table doesn't have to."""

    model_config = ConfigDict(extra="forbid")

    id: int
    store_id: int
    report_date: str  # YYYY-MM-DD
    taxable_sales: float = 0.0
    non_taxable: float = 0.0
    sales_tax: float = 0.0
    money_transfer: float = 0.0
    money_order: float = 0.0
    cash_expense: float = 0.0
    check_expense: float = 0.0
    cash_deposit: float = 0.0
    checks_deposit: float = 0.0
    safe_balance: float = 0.0
    over_short: float = 0.0
    locked: bool = False
    notes: str = ""
    total_receipts: float
    total_disbursements: float
    net: float


class DailyReportResponse(BaseModel):
    """Wrapped single-report response. None when the store hasn't
    logged a report on that date — clients distinguish via 404 at
    the Controller layer."""

    model_config = ConfigDict(extra="forbid")

    report: DailyReportRow


class PeriodSummaryResponse(BaseModel):
    """Date-range payload. `rows` are per-day; summary fields are
    sums across them."""

    model_config = ConfigDict(extra="forbid")

    rows: list[DailyReportRow] = Field(default_factory=list)
    total_receipts: float
    total_disbursements: float
    net: float
    days_logged: int


class DailyReportUpdateRequest(BaseModel):
    """PUT body for /daily/{store_id}/{date}. Only the editable
    top-level totals + notes — line-item-derived fields
    (cash_purchases, drops, etc.) come from their own tables and
    aren't writable here. Every numeric field is optional so the
    SPA can submit a partial form (only what the cashier edited).
    """

    model_config = ConfigDict(extra="forbid")

    taxable_sales:           float | None = None
    non_taxable:             float | None = None
    sales_tax:               float | None = None
    bill_payment_charge:     float | None = None
    phone_recargas:          float | None = None
    boost_mobile:            float | None = None
    money_order:             float | None = None
    check_cashing_fees:      float | None = None
    return_check_hold_fees:  float | None = None
    forward_balance:         float | None = None
    from_bank:               float | None = None
    rebates_commissions:     float | None = None
    cash_deposit:            float | None = None
    safe_balance:            float | None = None
    payroll_expense:         float | None = None
    over_short:              float | None = None
    notes:                   str = ""
