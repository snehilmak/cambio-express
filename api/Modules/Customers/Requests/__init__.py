"""Customers module — Pydantic request/response schemas.

``extra="forbid"`` is set on every model — drift between the
service output dict and the schema fails the response validator
instead of silently producing partial JSON.
"""
from api.Modules.Customers.Requests.customers import (
    CustomerResponse,
    CustomerRow,
    CustomerSearchResponse,
    CustomerUpsertRequest,
    CustomerUpsertResponse,
)
from api.Modules.Customers.Requests.merge import (
    CustomerMergeRequest,
    CustomerMergeResponse,
)
from api.Modules.Customers.Requests.recent_recipients import (
    RecentRecipientRow,
    RecentRecipientsResponse,
)

__all__ = [
    "CustomerMergeRequest",
    "CustomerMergeResponse",
    "CustomerResponse",
    "CustomerRow",
    "CustomerSearchResponse",
    "CustomerUpsertRequest",
    "CustomerUpsertResponse",
    "RecentRecipientRow",
    "RecentRecipientsResponse",
]
