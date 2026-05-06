"""Transfers module — Pydantic request/response schemas.

`extra="forbid"` everywhere so service-output drift fails the
response validator instead of silently producing partial JSON.
"""
from api.Modules.Transfers.Requests.transfers import (
    TransferListResponse,
    TransferResponse,
    TransferRow,
)

__all__ = [
    "TransferListResponse",
    "TransferResponse",
    "TransferRow",
]
