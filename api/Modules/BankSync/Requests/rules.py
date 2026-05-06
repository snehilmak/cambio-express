"""Pydantic schemas for the bank-rules list endpoint."""
from pydantic import BaseModel, ConfigDict, Field


class BankRuleRow(BaseModel):
    """One operator-managed BankRule. Same fields the
    /bank/rules HTML page exposes; the React rules-manager UI will
    consume the same shape."""

    model_config = ConfigDict(extra="forbid")

    id: int
    enabled: bool
    priority: int
    desc_match_type: str = ""
    desc_match_value: str = ""
    sign_filter: str = ""
    amount_min_cents: int | None = None
    amount_max_cents: int | None = None
    account_filter_id: int | None = None
    account_filter_label: str = ""  # nickname or ••last4 of the account
    target_kind: str
    auto_post: bool = True
    description: str = ""
    match_count: int = 0
    last_matched_at: str = ""  # ISO datetime, "" if never matched


class BankRuleListResponse(BaseModel):
    """Envelope for the /bank/rules read endpoint. Order matches the
    Repository: priority asc, id asc tie-break — the same order the
    auto-categorize sync walks them in, so what the UI shows is the
    actual evaluation order."""

    model_config = ConfigDict(extra="forbid")

    rows: list[BankRuleRow] = Field(default_factory=list)
    total: int
