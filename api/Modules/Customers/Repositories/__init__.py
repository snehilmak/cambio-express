"""Customers module — Repositories.

SQL-only helpers. No business logic, no policy decisions, no Pydantic
shapes. Each fn takes the SQLAlchemy `Session` as the first arg so
the same code runs under Flask (Flask-SQLAlchemy session) or
standalone FastAPI (request-scoped `Depends(get_db)` session).
"""
from api.Modules.Customers.Repositories.customers import (
    find_by_id_in_stores,
    find_by_phone_in_stores,
    recent_customers,
    search_by_substring,
    sibling_store_ids,
)

__all__ = [
    "find_by_id_in_stores",
    "find_by_phone_in_stores",
    "recent_customers",
    "search_by_substring",
    "sibling_store_ids",
]
