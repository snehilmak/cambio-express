"""Pydantic schemas for the team-roster endpoints."""
from pydantic import BaseModel, ConfigDict, Field


class TeamMemberRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    name: str
    is_active: bool


class TeamListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    members: list[TeamMemberRow]


class TeamMemberCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., min_length=1, max_length=120)


class TeamMemberUpdateRequest(BaseModel):
    """PATCH-style update — fields omitted are left alone."""

    model_config = ConfigDict(extra="forbid")

    name:      str | None  = Field(None, min_length=1, max_length=120)
    is_active: bool | None = None
