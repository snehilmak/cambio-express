"""Schemas for the customer-merge endpoint.

Takes a ``loser_id`` in the request body (the row that gets
deleted) — the ``winner_id`` lives in the path. Returns a tally
of what changed so the SPA can show a confirmation toast.
"""
from pydantic import BaseModel, ConfigDict, Field


class CustomerMergeRequest(BaseModel):
    """Body for ``POST /customers/{winner_id}/merge``. The winner
    is in the path; the loser goes here so the eligibility check
    has both IDs in one place."""

    model_config = ConfigDict(extra="forbid")

    loser_id: int = Field(..., ge=1, description=(
        "ID of the duplicate customer to delete. All Transfers "
        "pointing at this row will be re-pointed to the winner."
    ))


class CustomerMergeResponse(BaseModel):
    """Shape returned to the SPA after a successful merge."""

    model_config = ConfigDict(extra="forbid")

    winner_id:           int
    loser_id:            int
    transfers_repointed: int
