"""Pydantic schemas for the ACH batches read-side."""
from pydantic import BaseModel, ConfigDict, Field


class BatchRow(BaseModel):
    """One ACH batch row. Mirrors the columns the legacy
    `/batches` table renders + the computed totals
    (transfers_total, variance, transfer_count) the SPA needs
    to colour the variance cell."""

    model_config = ConfigDict(extra="forbid")

    id: int
    ach_date: str         # YYYY-MM-DD
    company: str
    batch_ref: str
    ach_amount: float
    status: str = "Pending"
    reconciled: bool = False
    transfer_dates: str = ""
    notes: str = ""
    # Server-precomputed totals so the SPA doesn't have to N+1
    # the transfers table per row.
    transfers_total: float
    variance: float
    transfer_count: int


class BatchListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rows: list[BatchRow] = Field(default_factory=list)
