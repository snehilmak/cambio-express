"""Pydantic schemas for the report-import read/preview surface.

The PDF is uploaded as base64 inside a JSON body (not multipart) so
the SPA can post it without FormData and the backend needs no
``python-multipart`` dependency. Parsing is in-memory only — nothing
is persisted (the operator keeps the original file).
"""
from pydantic import BaseModel, ConfigDict, Field


# ~15 MB decoded ceiling. These daily reports are a few hundred KB; the
# cap is a guard against someone posting a huge file, not a real limit.
MAX_PDF_BYTES = 15 * 1024 * 1024


class IntermexParseRequest(BaseModel):
    """Upload body: the report PDF, base64-encoded."""

    model_config = ConfigDict(extra="forbid")

    # base64 of the raw PDF bytes. Length-capped generously so a
    # malformed/huge payload is rejected before we try to decode it.
    content_base64: str = Field(..., min_length=1, max_length=MAX_PDF_BYTES * 2)
    filename: str = ""


class IntermexCommitRequest(BaseModel):
    """Commit body: the same base64 PDF the operator reviewed, plus the
    store + day to attach it to. The bytes are re-parsed server-side —
    the client never sends money numbers, so a tampered review can't
    poison the ledger. ``report_date`` is the day the operator is
    editing (may differ from the report's own Fecha; the SPA warns)."""

    model_config = ConfigDict(extra="forbid")

    content_base64: str = Field(..., min_length=1, max_length=MAX_PDF_BYTES * 2)
    filename: str = ""
    store_id: int = Field(..., ge=1)
    report_date: str  # YYYY-MM-DD — the day to attach the giros to


class IntermexCommitResponse(BaseModel):
    """Commit outcome + reconcile comparison against already-logged
    transfers. ``matches_logged`` is True when the report's send total
    matches the Intermex transfers the store already logged for the
    day (within half a cent) — the "these agree" signal."""

    model_config = ConfigDict(extra="forbid")

    company: str
    giros_committed: int
    amount: float
    fees: float
    federal_tax: float
    committed_total: float
    grand_total: float
    logged_amount: float
    logged_total: float
    previous_saved_total: float
    matches_logged: bool


class IntermexTxnRowResponse(BaseModel):
    """One parsed transaction row (Giro / money order / bill payment).

    ``federal_tax`` is populated only for Giros. ``reconciles`` is the
    Giros invariant (send + fee + tax == total); informational for the
    other sections."""

    model_config = ConfigDict(extra="forbid")

    section: str
    confirm_number: str
    send_amount: float
    fee: float
    federal_tax: float
    total_collected: float
    cashier: str
    cancelled: bool
    replacement: bool
    reconciles: bool


class SectionTotalsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    count: int
    processed: int
    voided: int
    amount: float
    fees: float
    balance: float


class IntermexReportResponse(BaseModel):
    """Parsed report preview. ``report_date`` is the report's own
    ``Fecha`` (may differ from the day the operator is editing — the
    SPA warns on a mismatch). ``all_reconcile`` is the safe-to-commit
    signal (every active Giro reconciles + matches the stated total)."""

    model_config = ConfigDict(extra="forbid")

    agency: str
    report_date: str | None  # ISO date, or null
    giros: list[IntermexTxnRowResponse]
    money_orders: list[IntermexTxnRowResponse]
    bill_payments: list[IntermexTxnRowResponse]
    giros_totals: SectionTotalsResponse | None
    money_order_totals: SectionTotalsResponse | None
    bill_payment_totals: SectionTotalsResponse | None
    all_reconcile: bool
