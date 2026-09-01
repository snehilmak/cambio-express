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
    # R-3: the saved access role this user follows, if any. The
    # roster and the user form show the role's NAME rather than a
    # generic "Custom access" pill.
    store_role_id: int | None = None
    store_role_name: str = ""


class AdminUserListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rows: list[AdminUserRow]


class AdminUserDetailResponse(BaseModel):
    """Single-user fetch payload for the Edit form prefill."""

    model_config = ConfigDict(extra="forbid")

    user: AdminUserRow


class AdminUserCreateRequest(BaseModel):
    """New logins are identified by email and/or phone — there is no
    username to type. At least one of `email` / `phone` must be
    present; the Service raises 422 when both are blank."""

    model_config = ConfigDict(extra="forbid")

    email:     str | None = Field(None, max_length=255)
    phone:     str | None = Field(None, max_length=40)
    password:  str = Field(..., min_length=1, max_length=200)
    full_name: str = Field("", max_length=120)
    role:      str = Field("employee", min_length=1, max_length=20)
    module_access: list[str] | None = Field(None, max_length=20)
    # R-2: optional custom-access overlay written at creation time
    # (resource → action → bool). None = pure role permissions.
    permissions: dict[str, dict[str, bool]] | None = None
    # R-3: put the new hire straight into a saved role. Takes
    # precedence over `permissions` — a named role IS a matrix, and
    # honouring both would leave the label describing access the
    # user does not have.
    store_role_id: int | None = None


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
