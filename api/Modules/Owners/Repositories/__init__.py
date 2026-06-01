"""Owners — Repositories.

Pure query functions for the Owners module. No business logic,
no Pydantic schemas, no audit logging. Caller is responsible for
permissions + commit lifecycle.

The Repository layer exists so Controllers don't accumulate
inline ``db.query(...).filter(...)`` boilerplate; new endpoints
should reach for an existing helper or add a new one here before
inlining SQL.
"""
from api.Modules.Owners.Repositories.connect_codes import (
    find_owner_code,
    get_store_names_map as get_store_names_for_codes,
    list_codes_for_owner,
)
from api.Modules.Owners.Repositories.store_links import find_link
from api.Modules.Owners.Repositories.stores import (
    get_store,
    get_store_names_map,
)
from api.Modules.Owners.Repositories.users import users_in_stores_query

__all__ = [
    "find_link",
    "find_owner_code",
    "get_store",
    "get_store_names_for_codes",
    "get_store_names_map",
    "list_codes_for_owner",
    "users_in_stores_query",
]
