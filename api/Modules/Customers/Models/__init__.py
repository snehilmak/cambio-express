"""Customers module — Models.

Re-exports the legacy SQLAlchemy classes from `app.py` during the
strangler-fig migration. Same pattern as Reports/Models: keep a
single ORM definition while both apps run side-by-side.

Models in scope:
- `Customer` — the per-store customer directory row.
- `Store` + `StoreOwnerLink` — needed to resolve the "owner
  umbrella" (sibling stores under the same owner). Customer queries
  scope on this list, not just the current store, so a multi-store
  owner sees one unified directory.
"""
from app import Customer, Store, StoreOwnerLink

__all__ = ["Customer", "Store", "StoreOwnerLink"]
