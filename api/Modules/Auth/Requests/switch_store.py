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


class MyStoresResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stores: list[SwitchableStoreRow]


class SwitchStoreRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    store_id: int = Field(..., ge=1)


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
