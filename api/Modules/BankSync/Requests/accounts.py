"""Pydantic schemas for the bank-accounts list endpoint."""
from pydantic import BaseModel, ConfigDict, Field


class BankAccountRow(BaseModel):
    """One connected bank account. Fields mirror what the
    /bank/transactions sidebar + the /bank/connect page render."""

    model_config = ConfigDict(extra="forbid")

    id: int
    institution_name: str = ""
    display_name: str = ""
    nickname: str = ""
    last4: str = ""
    label: str = ""  # nickname → ••last4 → "Account" fallback
    category: str = ""  # checking / savings / credit / other
    subcategory: str = ""
    currency: str = "usd"
    last_balance_cents: int = 0
    last_balance: float = 0.0
    last_balance_as_of: str = ""  # ISO datetime
    enabled: bool = True
    connected_at: str = ""  # ISO datetime
    disconnected_at: str = ""  # ISO datetime, "" if still connected


class BankAccountListResponse(BaseModel):
    """Envelope for /bank/accounts. Order matches the Repository:
    nickname → display_name → institution_name (case-insensitive)
    + id tie-break for stable rendering."""

    model_config = ConfigDict(extra="forbid")

    rows: list[BankAccountRow] = Field(default_factory=list)
    total: int
