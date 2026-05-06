"""Customers module — Pydantic request/response schemas.

Wire-format contracts for the customer search + upsert endpoints.
Both surfaces (JSON via FastAPI and the legacy Flask response shape)
must match the structure exposed here.

`extra="forbid"` is set on every model — drift between the service
output dict and the schema fails the response validator instead of
silently producing partial JSON.
"""
from api.Modules.Customers.Requests.customers import (
    CustomerRow,
    CustomerSearchResponse,
    CustomerUpsertRequest,
    CustomerUpsertResponse,
)

__all__ = [
    "CustomerRow",
    "CustomerSearchResponse",
    "CustomerUpsertRequest",
    "CustomerUpsertResponse",
]
