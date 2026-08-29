"""Pydantic schemas for the per-store user-management endpoints."""
from pydantic import BaseModel, ConfigDict, Field


class AdminUserRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id:         int
    username:   str
    full_name:  str
    role:       str
    is_active:  bool
    created_at: str  # ISO timestamp; "" if missing
    # None = every module the store has; a list restricts this
    # user's visible modules (subset of MODULE_FLAG_KEYS).
    module_access: list[str] | None
    # True when the user carries a per-user permission overlay
    # (R-1) — custom access instead of their role's defaults.
    has_custom_permissions: bool = False


class AdminUserListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rows: list[AdminUserRow]


class AdminUserDetailResponse(BaseModel):
    """Single-user fetch payload for the Edit form prefill."""

    model_config = ConfigDict(extra="forbid")

    user: AdminUserRow


class AdminUserCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username:  str = Field(..., min_length=1, max_length=80)
    password:  str = Field(..., min_length=1, max_length=200)
    full_name: str = Field("", max_length=120)
    role:      str = Field("employee", min_length=1, max_length=20)
    module_access: list[str] | None = Field(None, max_length=20)


class AdminUserUpdateRequest(BaseModel):
    """PATCH-style update — fields omitted are left alone.

    `password` is treated as "blank → keep current hash" by the
    Service, mirroring the legacy form. Required-min-length on
    the field would force every Edit submit to include a
    password, breaking the existing UX, so we accept an empty
    string and let the Service skip it.
    """

    model_config = ConfigDict(extra="forbid")

    full_name: str  | None = Field(None, max_length=120)
    # PATCH semantics: omitted = unchanged; null = all modules;
    # a list = restrict to those modules.
    module_access: list[str] | None = Field(None, max_length=20)
    role:      str  | None = Field(None, min_length=1, max_length=20)
    is_active: bool | None = None
    password:  str  | None = Field(None, max_length=200)
