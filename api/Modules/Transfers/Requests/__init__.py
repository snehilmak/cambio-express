"""Transfers module — Pydantic request/response schemas.

`extra="forbid"` everywhere so service-output drift fails the
response validator instead of silently producing partial JSON.
"""
from api.Modules.Transfers.Requests.transfers import (
    CreateTransferRequest,
    TransferListResponse,
    TransferResponse,
    TransferRow,
)

__all__ = [
    "CreateTransferRequest",
    "TransferListResponse",
    "TransferResponse",
    "TransferRow",
]
