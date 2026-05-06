"""Customers module — Services.

Business logic. Composes Repository SQL helpers into the customer
upsert (used by the transfer form) and the autocomplete search
(used by `/api/customers/search`). No HTTP-layer concerns here —
those live in Controllers.

Migrated from `app.py`:
- `find_or_upsert_customer` → `upsert`
- `/api/customers/search` body → `search`

Both keep the owner-umbrella scoping rule (CLAUDE.md invariant #5):
sibling stores share customers, unrelated stores stay isolated.
"""
from api.Modules.Customers.Services.customers import (
    search,
    upsert,
)

__all__ = ["search", "upsert"]
