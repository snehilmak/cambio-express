"""Superadmin — Repositories.

Pure query functions for the cross-store / platform-level
endpoints. No permission checks (superadmin gate stays in the
Controller), no Pydantic, no audit logging.

The Repository layer exists so the 1670-line Controllers file
doesn't keep accumulating inline ``db.query()`` boilerplate; new
endpoints should reach for a helper here or add one.
"""
from api.Modules.Superadmin.Repositories.audit import (
    superadmin_audit_query,
)
from api.Modules.Superadmin.Repositories.discounts import (
    get_discount_code,
    list_discount_codes,
)
from api.Modules.Superadmin.Repositories.stores import (
    count_all_stores,
    get_store_by_slug,
    list_all_stores,
    list_all_stores_newest_first,
    list_stores_by_ids,
)
from api.Modules.Superadmin.Repositories.users import (
    count_all_users,
    list_active_admins_for_store,
    list_users_in_store,
    list_users_with_store_query,
)
from api.Modules.Superadmin.Repositories.webhooks import (
    email_events_query,
)

__all__ = [
    "count_all_stores",
    "count_all_users",
    "email_events_query",
    "get_discount_code",
    "get_store_by_slug",
    "list_active_admins_for_store",
    "list_all_stores",
    "list_all_stores_newest_first",
    "list_discount_codes",
    "list_stores_by_ids",
    "list_users_in_store",
    "list_users_with_store_query",
    "superadmin_audit_query",
]
