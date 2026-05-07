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
