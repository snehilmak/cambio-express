"""Pydantic schemas for the bank-transactions list endpoint."""
from pydantic import BaseModel, ConfigDict, Field


class BankTransactionRow(BaseModel):
    """One row in the /bank/transactions list. Wire shape mirrors
    what the legacy template renders — id, date, label, amount in
    dollars, category, etc."""

    model_config = ConfigDict(extra="forbid")

    id: int
    posted_at: str = ""  # ISO datetime, "" if pending
    description: str = ""
    amount_cents: int
    amount: float  # amount_cents / 100, signed
    currency: str = "usd"
    status: str = "posted"
    category_slug: str = ""
    account_id: int
    account_label: str = ""  # nickname or ••last4


class BankTransactionListResponse(BaseModel):
    """Paginated response envelope. Mirrors the partial-render JSON
    shape the legacy /bank/transactions page already returns."""

    model_config = ConfigDict(extra="forbid")

    rows: list[BankTransactionRow] = Field(default_factory=list)
    total: int
    page: int
    per_page: int
    total_pages: int
    page_total_cents: int
    uncategorized_count: int
