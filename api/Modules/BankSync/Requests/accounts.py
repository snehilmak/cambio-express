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


# ── Stripe Financial Connections connect flow ─────────────


class BankConnectResponse(BaseModel):
    """`POST /api/v2/bank/connect` envelope — minted FC session.

    The SPA hands `clientSecret` to `stripe.collectFinancialConnectionsAccounts()`,
    then POSTs `sessionId` back to `/connect/complete` to trigger
    server-side persistence.  `publishableKey` lets the SPA
    initialise Stripe.js without round-tripping for the env var.
    """

    model_config = ConfigDict(extra="forbid")

    clientSecret: str
    sessionId: str
    publishableKey: str


class BankConnectCompleteRequest(BaseModel):
    """`POST /api/v2/bank/connect/complete` body — the SPA hands
    back the FC session id after Stripe.js resolves so the
    server can fetch + persist the linked accounts."""

    model_config = ConfigDict(extra="forbid")

    sessionId: str


class BankConnectCompleteResponse(BaseModel):
    """Result of persisting an FC session's accounts."""

    model_config = ConfigDict(extra="forbid")

    accounts_added: int
    accounts_total: int


class BankRefreshResponse(BaseModel):
    """Result of a manual balance refresh."""

    model_config = ConfigDict(extra="forbid")

    accounts_refreshed: int
    error: str = ""


class BankSyncTransactionsResponse(BaseModel):
    """Result of a manual transaction sync."""

    model_config = ConfigDict(extra="forbid")

    new_rows: int
    total_seen: int
    error: str = ""
