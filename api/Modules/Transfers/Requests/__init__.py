"""Transfers module — Pydantic request/response schemas.

`extra="forbid"` everywhere so service-output drift fails the
response validator instead of silently producing partial JSON.
"""
from api.Modules.Transfers.Requests.receipt import (
    ReceiptStore,
    ReceiptTransfer,
    TransferReceiptResponse,
)
from api.Modules.Transfers.Requests.transfers import (
    CreateTransferRequest,
    EmployeeRow,
    RosterResponse,
    TransferListResponse,
    TransferResponse,
    TransferRow,
)

__all__ = [
    "CreateTransferRequest",
    "EmployeeRow",
    "ReceiptStore",
    "ReceiptTransfer",
    "RosterResponse",
    "TransferListResponse",
    "TransferReceiptResponse",
    "TransferResponse",
    "TransferRow",
]
