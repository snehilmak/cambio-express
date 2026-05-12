"""Pydantic schemas for the daily-book read-side."""
from pydantic import BaseModel, ConfigDict, Field


class DailyReportRow(BaseModel):
    """One day's roll-up. Pre-computes receipts / disbursements /
    net so the React table doesn't have to.

    Carries the full DailyReport field set — the editor hydrates
    every input from this payload, line-item-derived fields display
    as read-only "Auto" tiles, and the real-time totals strip sums
    them client-side as the cashier types."""

    model_config = ConfigDict(extra="forbid")

    id: int
    store_id: int
    report_date: str  # YYYY-MM-DD
    # Sales
    taxable_sales: float = 0.0
    non_taxable: float = 0.0
    sales_tax: float = 0.0
    # Receipts (operator-editable)
    bill_payment_charge: float = 0.0
    phone_recargas: float = 0.0
    boost_mobile: float = 0.0
    money_transfer: float = 0.0
    money_order: float = 0.0
    check_cashing_fees: float = 0.0
    return_check_hold_fees: float = 0.0
    forward_balance: float = 0.0
    from_bank: float = 0.0
    rebates_commissions: float = 0.0
    # Receipts (line-item derived — read-only in editor)
    return_check_paid_back: float = 0.0
    other_cash_in: float = 0.0
    # Disbursements (operator-editable)
    cash_deposit: float = 0.0
    safe_balance: float = 0.0
    payroll_expense: float = 0.0
    # Disbursements (line-item derived — read-only in editor)
    cash_purchases: float = 0.0
    cash_expense: float = 0.0
    check_purchases: float = 0.0
    check_expense: float = 0.0
    outside_cash_drops: float = 0.0
    checks_deposit: float = 0.0
    other_cash_out: float = 0.0
    # Other
    over_short: float = 0.0
    locked: bool = False
    notes: str = ""
    # ISO datetime, or "" when unlocked
    locked_at: str = ""
    # Derived
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


class LineItemRow(BaseModel):
    """One DailyLineItem (drop, check deposit, cash expense,
    return payback, etc.) on a daily report. The line-item
    family is discriminated by `kind`; see LINE_ITEM_KINDS."""

    model_config = ConfigDict(extra="forbid")

    id: int
    kind: str
    at_time: str  # HH:MM
    amount: float
    note: str = ""
    # Non-null when the line item was auto-created by marking a
    # ReturnCheck recovered. Manual deletes are blocked for these
    # — the SPA disables the delete button when this is set so the
    # cashier can't strip a payback that's mirrored from the
    # Return Checks page.
    return_check_id: int | None = None


class LineItemListResponse(BaseModel):
    """Wrapped list. Optional kind filter narrows the result;
    omit to return every kind for the day."""

    model_config = ConfigDict(extra="forbid")

    items: list[LineItemRow]


class LineItemCreateRequest(BaseModel):
    """POST body for /daily/{store}/{date}/line-items. Validates
    against the same parsers the legacy form uses (`parse_at_time`,
    `parse_amount`) so error messages match for cutover parity."""

    model_config = ConfigDict(extra="forbid")

    kind: str  # validated server-side against LINE_ITEM_KINDS
    at_time: str  # HH:MM
    amount: float  # > 0; the Service rejects ≤0
    note: str = ""


class TransferCompanyTotalsResponse(BaseModel):
    """One company's roll-up inside the day's transfer-summary
    response. Mirrors the editable columns the legacy Jinja MT
    table showed; the React Money Transfers tab renders this
    read-only with an "Auto" pill — operator overrides go through
    the receipts tab's `money_transfer` field."""

    model_config = ConfigDict(extra="forbid")

    company: str
    count: int
    amount: float
    fees: float
    federal_tax: float
    commission: float
    total: float


class TransfersSummaryResponse(BaseModel):
    """Auto-fill payload for the Daily Book's Money Transfers tab.
    Aggregates active (non-cancelled) Transfer rows by company for
    a single (store, send_date). Zero-row days still return one
    entry per active company so the table renders consistently."""

    model_config = ConfigDict(extra="forbid")

    companies: list[str]
    by_company: list[TransferCompanyTotalsResponse]
    grand_total: float


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
