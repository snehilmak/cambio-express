"""Schemas for the active-sessions panel.

Powers ``GET /api/v2/auth/sessions`` (list) +
``DELETE /api/v2/auth/sessions/{session_id}`` (single-revoke) +
``DELETE /api/v2/auth/sessions/others`` (revoke-all-except-mine).
"""
from pydantic import BaseModel, ConfigDict


class ActiveSessionRow(BaseModel):
    """One refresh-token chain (== one browser / one login)."""

    model_config = ConfigDict(extra="forbid")

    session_id:   str
    user_agent:   str
    ip_address:   str
    # ISO-8601. ``started_at`` is the head-row's created_at — for a
    # session that's been refreshing for two weeks, this is the
    # most recent rotation, not the original login.
    started_at:   str
    last_used_at: str
    expires_at:   str
    is_current:   bool


class ActiveSessionsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sessions: list[ActiveSessionRow]


class SessionRevokeResponse(BaseModel):
    """Echoed back after a revoke call so the SPA knows how many
    refresh rows actually changed state (chains span N rows after
    a long-lived login)."""

    model_config = ConfigDict(extra="forbid")

    revoked: int
