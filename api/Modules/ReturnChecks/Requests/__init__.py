"""ReturnChecks — Pydantic schemas."""
from pydantic import BaseModel, ConfigDict, Field


class ReturnCheckRow(BaseModel):
    """One bounced-check row. Mirrors the columns the legacy
    /return-checks list page renders."""

    model_config = ConfigDict(extra="forbid")

    id: int
    bounced_on: str  # YYYY-MM-DD
    customer_name: str
    check_number: str = ""
    payer_bank: str = ""
    amount: float
    status: str
    status_changed_on: str = ""  # "" when pending
    notes: str = ""
    recovered_total: float = 0.0
    payment_count: int = 0


class ReturnCheckListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rows: list[ReturnCheckRow]


class ReturnCheckResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    return_check: ReturnCheckRow


class ReturnCheckWriteRequest(BaseModel):
    """POST/PUT body. Status transitions go through dedicated
    endpoints, not via this schema."""

    model_config = ConfigDict(extra="forbid")

    bounced_on:    str   = Field(..., min_length=10, max_length=10)
    customer_name: str   = Field(..., min_length=1, max_length=120)
    check_number:  str   = Field("", max_length=40)
    payer_bank:    str   = Field("", max_length=120)
    amount:        float = Field(..., gt=0)
    notes:         str   = Field("", max_length=2000)


class ReturnCheckPaymentRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    return_check_id: int
    amount: float
    paid_on: str
    method: str = ""
    notes: str = ""


class ReturnCheckPaymentsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    payments: list[ReturnCheckPaymentRow]


__all__ = [
    "ReturnCheckListResponse",
    "ReturnCheckPaymentRow",
    "ReturnCheckPaymentsResponse",
    "ReturnCheckResponse",
    "ReturnCheckRow",
    "ReturnCheckWriteRequest",
]
