"""Owner store-switching schemas (U-2, the single-dashboard
principle): an owner enters a store and sees exactly the same
store view as the users they create — the Switch Store modal just
changes which store that one dashboard shows.
"""
from pydantic import BaseModel, ConfigDict, Field


class SwitchableStoreRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    store_id: int
    name: str
    slug: str
    address: str
    # The store the caller's current token is scoped to (if any) —
    # the modal marks it with the active radio.
    is_current: bool
    # The owner's home store (User.store_id) — the deterministic
    # auto-enter target after login when no store is remembered.
    # All-false for legacy owners created without a home store.
    is_home: bool


class MyStoresResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stores: list[SwitchableStoreRow]


class SwitchStoreRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    store_id: int = Field(..., ge=1)


class OwnerAddStoreRequest(BaseModel):
    """POST body for /auth/my-stores — an existing owner adds a new
    store under their umbrella (U-5a, the switcher's "+" button).
    The new store gets its own trial window; subscriptions stay
    per store."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., min_length=1, max_length=120)
    business_type: str = Field(
        "cstore",
        pattern="^(cstore|gas_station|grocery|msb_hybrid)$",
    )
    phone:   str = Field("", max_length=40)
    address: str = Field("", max_length=240)


class SwitchStoreResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    access_token: str
    store_id: int
    store_name: str
    role: str
    expires_in: int
    # Identity-cache fields (mirrors LoginResponse) so the SPA can
    # persist the new claims without decoding the httpOnly cookie.
    user_id: int
    username: str
    full_name: str
    permissions: list[str]
    owner_id: int
