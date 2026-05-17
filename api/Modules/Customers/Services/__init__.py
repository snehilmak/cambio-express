"""Customers module — Services.

Business logic. Composes Repository SQL helpers into the customer
upsert (used by the transfer form), the autocomplete search, the
recent-recipients chip lookup, and the duplicate-merge tool.
No HTTP-layer concerns here — those live in Controllers.

All keep the owner-umbrella scoping rule (CLAUDE.md invariant #5):
sibling stores share customers, unrelated stores stay isolated.
"""
from api.Modules.Customers.Services.customers import (
    search,
    upsert,
)
from api.Modules.Customers.Services.merge import (
    CustomerMergeError,
    CustomerMergeResult,
    CustomerNotFoundError,
    SameCustomerError,
    merge_customers,
)
from api.Modules.Customers.Services.phone_codes import (
    PHONE_COUNTRY_CODES,
)
from api.Modules.Customers.Services.recent_recipients import (
    RecentRecipient,
    list_recent_recipients,
)

__all__ = [
    "CustomerMergeError",
    "CustomerMergeResult",
    "CustomerNotFoundError",
    "PHONE_COUNTRY_CODES",
    "RecentRecipient",
    "SameCustomerError",
    "list_recent_recipients",
    "merge_customers",
    "search",
    "upsert",
]
