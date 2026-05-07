"""Pydantic schemas for the login endpoint."""
from pydantic import BaseModel, ConfigDict, Field


class LoginRequest(BaseModel):
    """POST body for /auth/login. `store_id` is None for the
    superadmin scope; positive integer otherwise."""

    model_config = ConfigDict(extra="forbid")

    username: str = Field(..., min_length=1, max_length=255)
    password: str = Field(..., min_length=1)
    store_id: int | None = None


class LoginCrossStoreRequest(BaseModel):
    """POST body for /auth/login-cross-store. The SPA's generic
    landing page doesn't know which store a user belongs to — this
    endpoint takes username + password only and looks up the
    user's home store across all stores (first match wins, like
    the legacy Flask `/login` POST). Employees get rejected here
    because they're expected to use their store's slug-scoped
    sign-in URL.
    """

    model_config = ConfigDict(extra="forbid")

    username: str = Field(..., min_length=1, max_length=255)
    password: str = Field(..., min_length=1)


class LoginResponse(BaseModel):
    """Successful-login response. `access_token` is the bearer JWT
    the client must send as `Authorization: Bearer <token>` on
    subsequent calls. `expires_in` is seconds until the token's
    `exp` claim — clients refresh before then to avoid an
    in-flight 401."""

    model_config = ConfigDict(extra="forbid")

    access_token: str
    token_type: str = "Bearer"
    expires_in: int = 30 * 60
    user_id: int
    username: str
    full_name: str = ""
    role: str
    store_id: int | None
    permissions: list[str]
