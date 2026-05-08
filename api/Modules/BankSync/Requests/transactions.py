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


class CategorizeRequest(BaseModel):
    """POST body for /bank/transactions/{txn_id}/categorize.

    `target_kind` is a slug from `BANK_CATEGORIES_NON_POSTING` or
    `_LINE_ITEM_KINDS` (e.g. "bank_charge_210", "cash_deposit").
    `post_to_daily=False` keeps the assignment metadata-only and
    skips creating the matching DailyLineItem (used when the
    operator wants the P&L tag without a daily-book mirror)."""

    model_config = ConfigDict(extra="forbid")

    target_kind: str = Field(..., min_length=1, max_length=60)
    post_to_daily: bool = True


class CategorizeResponse(BaseModel):
    """Returned from categorize / uncategorize. Echoes the row's
    new category state so the SPA can update without re-fetching."""

    model_config = ConfigDict(extra="forbid")

    transaction: BankTransactionRow
