"""Pydantic schemas for the team-roster endpoints."""
from pydantic import BaseModel, ConfigDict, Field


class TeamMemberRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    name: str
    is_active: bool
    # USD/hour pay rate used by the time-clock paystub view.
    # 0.0 means "not configured yet" — the paystub shows a dash
    # in the gross-pay column.
    hourly_rate: float = 0.0


class TeamListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    members: list[TeamMemberRow]


class TeamMemberCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name:        str   = Field(..., min_length=1, max_length=120)
    hourly_rate: float = Field(0.0, ge=0.0, le=10_000.0)


class TeamMemberUpdateRequest(BaseModel):
    """PATCH-style update — fields omitted are left alone."""

    model_config = ConfigDict(extra="forbid")

    name:        str   | None = Field(None, min_length=1, max_length=120)
    is_active:   bool  | None = None
    hourly_rate: float | None = Field(None, ge=0.0, le=10_000.0)
