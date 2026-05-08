"""FeatureFlags — Pydantic request/response schemas."""
from pydantic import BaseModel, ConfigDict, Field


class FeatureFlagRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    key: str
    label: str
    description: str
    enabled_by_default: bool
    created_at: str


class FeatureFlagListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rows: list[FeatureFlagRow]
    total: int


class FeatureFlagCreateRequest(BaseModel):
    """POST body for /feature-flags. Mirrors the legacy
    /superadmin/features/new form. `key` is slug-style — lowercase
    letters, digits, underscores; the convention is `addon_<thing>`
    for paid add-ons or `<feature>` for general toggles."""
    model_config = ConfigDict(extra="forbid")

    key: str = Field(..., min_length=1, max_length=60,
                     pattern="^[a-z0-9_]+$")
    label: str = Field("", max_length=120)
    description: str = Field("", max_length=2000)
    enabled_by_default: bool = True


class FeatureFlagToggleRequest(BaseModel):
    """POST body for /feature-flags/{key}/toggle. Explicit
    `enabled_by_default` so callers don't accidentally flip the
    wrong way on stale data."""
    model_config = ConfigDict(extra="forbid")

    enabled_by_default: bool


class FeatureFlagResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    flag: FeatureFlagRow


__all__ = [
    "FeatureFlagCreateRequest",
    "FeatureFlagListResponse",
    "FeatureFlagResponse",
    "FeatureFlagRow",
    "FeatureFlagToggleRequest",
]
