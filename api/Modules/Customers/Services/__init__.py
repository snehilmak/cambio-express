"""Customers module — Services.

Business logic. Composes Repository SQL helpers into the customer
upsert (used by the transfer form), the autocomplete search
(used by `/api/customers/search`), and the recent-recipients
chip lookup. No HTTP-layer concerns here — those live in Controllers.

Migrated from `app.py`:
- `find_or_upsert_customer` → `upsert`
- `/api/customers/search` body → `search`
- `/api/customers/<id>/recent-recipients` body → `list_recent_recipients`

All keep the owner-umbrella scoping rule (CLAUDE.md invariant #5):
sibling stores share customers, unrelated stores stay isolated.
"""
from api.Modules.Customers.Services.customers import (
    search,
    upsert,
)
from api.Modules.Customers.Services.recent_recipients import (
    RecentRecipient,
    list_recent_recipients,
)

__all__ = [
    "RecentRecipient",
    "list_recent_recipients",
    "search",
    "upsert",
]
