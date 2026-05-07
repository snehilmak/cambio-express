"""Pydantic schemas for the transfer ledger.

`TransferRow` matches the fields the React frontend (and the legacy
JS in `_transfers_table.html`) consumes — not every column on the
`Transfer` model. Backend-only fields (commission, internal_notes,
audit columns) stay out of the wire shape until a controller
explicitly opts them in.
"""
from pydantic import BaseModel, ConfigDict, Field


class TransferRow(BaseModel):
    """One row in the `/transfers` table. Optional fields default to
    empty/zero so the controller's adapter can treat empty DB cells
    as legal placeholders rather than 422-ing the response."""

    model_config = ConfigDict(extra="forbid")

    id: int
    send_date: str  # YYYY-MM-DD
    company: str
    service_type: str = "Money Transfer"
    sender_name: str
    recipient_name: str = ""
    country: str = ""
    confirm_number: str = ""
    send_amount: float
    fee: float = 0.0
    federal_tax: float = 0.0
    total_collected: float
    status: str = "Sent"
    batch_id: str = ""
    employee_name: str = ""


class TransferListResponse(BaseModel):
    """Paginated response envelope. Mirrors the legacy `partial=1`
    JSON shape (rows + pagination meta + page-amount header) so the
    React frontend and the legacy JS swap pattern can consume the
    same payload."""

    model_config = ConfigDict(extra="forbid")

    rows: list[TransferRow] = Field(default_factory=list)
    total: int
    page: int
    per_page: int
    total_pages: int
    page_amount: float


class TransferResponse(BaseModel):
    """Single-transfer wrapped response. Uses the same TransferRow
    shape as the list endpoint so the React detail view and table
    can reuse the row component."""

    model_config = ConfigDict(extra="forbid")

    transfer: TransferRow


class CreateTransferRequest(BaseModel):
    """POST body for /transfers. Mirrors the legacy `new_transfer`
    Flask form fields. `federal_tax` is intentionally absent — the
    server always recomputes from `(send_amount, service_type,
    country, store)` so the client can't lie about the tax rate.
    """

    model_config = ConfigDict(extra="forbid")

    send_date: str  # YYYY-MM-DD
    company: str = Field(..., min_length=1, max_length=30)
    service_type: str = Field("Money Transfer", max_length=30)
    sender_name: str = Field(..., min_length=1, max_length=120)
    send_amount: float = Field(..., ge=0)
    fee: float = Field(0.0, ge=0)
    commission: float = Field(0.0, ge=0)
    recipient_name: str = Field("", max_length=120)
    country: str = Field("", max_length=60)
    recipient_phone: str = Field("", max_length=40)
    sender_phone: str = Field("", max_length=40)
    sender_phone_country: str = Field("+1", max_length=8)
    sender_address: str = Field("", max_length=255)
    sender_dob: str = Field("", max_length=10)  # YYYY-MM-DD or empty
    confirm_number: str = Field("", max_length=60)
    status: str = Field("Sent", max_length=30)
    status_notes: str = Field("", max_length=255)
    batch_id: str = Field("", max_length=60)
    internal_notes: str = Field("", max_length=255)
    employee_id: int | None = None
    customer_id: int | None = None
