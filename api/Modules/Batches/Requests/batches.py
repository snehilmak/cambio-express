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


class BatchResponse(BaseModel):
    """Single-batch payload used by the create / edit / detail
    endpoints. Same shape as a row from the list endpoint."""

    model_config = ConfigDict(extra="forbid")

    batch: BatchRow


class BatchWriteRequest(BaseModel):
    """POST/PUT body for /batches. Mirrors the legacy form's
    fields. Server pads `transfer_count` / `variance` /
    `transfers_total` from the live Transfer table after the
    write."""

    model_config = ConfigDict(extra="forbid")

    ach_date:        str = Field(..., min_length=10, max_length=10)  # YYYY-MM-DD
    company:         str = Field(..., min_length=1, max_length=30)
    batch_ref:       str = Field(..., min_length=1, max_length=60)
    ach_amount:      float = Field(..., ge=0)
    transfer_dates:  str = Field("", max_length=60)
    status:          str = Field("Pending", max_length=30)
    reconciled:      bool = False
    notes:           str = Field("", max_length=255)


class BatchTransfersResponse(BaseModel):
    """Transfers linked to one ACH batch by `batch_id ==
    batch_ref`. Same TransferRow shape the Transfers module
    uses, mirrored here so the Batches read-side stays
    self-contained."""

    model_config = ConfigDict(extra="forbid")

    transfers: list["BatchLinkedTransferRow"]


class BatchLinkedTransferRow(BaseModel):
    """Subset of Transfer columns the SPA's batch-detail page
    renders. Kept narrower than the full TransferRow because
    cross-module Pydantic re-export gets messy and the SPA
    doesn't need every field here."""

    model_config = ConfigDict(extra="forbid")

    id: int
    send_date: str
    company: str
    sender_name: str
    recipient_name: str = ""
    country: str = ""
    confirm_number: str = ""
    send_amount: float
    fee: float = 0.0
    federal_tax: float = 0.0
    total_collected: float
    status: str = "Sent"


# Forward reference resolution
BatchTransfersResponse.model_rebuild()
