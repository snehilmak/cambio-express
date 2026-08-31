"""Owner-side bulk user creation.

Lets an owner add the same login to many of their linked stores
in one POST. Use case: a regional manager / new admin who needs
identical credentials across every store the owner runs.

Implementation note: this creates N independent ``User`` rows
(one per store, all sharing the same username + password). The
``User`` schema is single-store-scoped today; users at sibling
stores stay logically separate but the operator types one
password to access them all. Multi-store users (one row, many
``store_id`` values) is a separate architectural item.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from api.Modules.Admin.Services.users import (
    UsernameTakenError,
    create_store_user,
)
from api.Modules.Owners.Repositories import get_store_names_map, store_ids_for_owner

VALID_ROLES = {"admin", "employee"}


def bulk_add_user_to_stores(
    db: Session,
    *,
    owner_id: int,
    store_ids: list[int],
    password: str,
    email: str = "",
    phone: str = "",
    full_name: str = "",
    role: str = "employee",
) -> list[dict[str, Any]]:
    """Create the same User across every requested store that's
    in the owner's umbrella. Returns one result row per
    requested store with one of three statuses:

      ``created``  — new User row inserted
      ``skipped``  — that store already had this person
      ``rejected`` — the store is not in the owner's umbrella

    The person is identified by email and/or phone, like every
    other new login (L-2). Creating the same identifier at several
    stores is the intended use here, and it's exactly the case the
    sign-in store-picker handles: one set of credentials, valid at
    several stores, so they choose which one to open.

    Caller commits. Per-store failures don't roll the whole
    batch back — each is reported in the response and the
    transaction keeps going (best-effort semantics, matching
    the SPA's "what happened to each one" table view).
    """
    from api.Modules.Auth.Services.identity import login_identifier

    if role not in VALID_ROLES:
        raise ValueError("Role must be 'admin' or 'employee'.")
    if not login_identifier(email, phone):
        raise ValueError(
            "An email address or phone number is required — it's how "
            "this person signs in.",
        )
    if not (password or ""):
        raise ValueError("Password is required.")
    if not store_ids:
        raise ValueError("Pick at least one store.")
    if len(store_ids) > 50:
        # Sanity cap — no umbrella in the wild has 50 stores.
        # Keeps a runaway bulk-create from racing the rate limiter.
        raise ValueError("Cannot target more than 50 stores in one call.")

    allowed = store_ids_for_owner(db, owner_id)
    name_lookup = get_store_names_map(db, list(set(store_ids)))

    results: list[dict[str, Any]] = []
    for sid in store_ids:
        store_name = name_lookup.get(sid, "")
        if sid not in allowed:
            results.append({
                "store_id": sid,
                "store_name": store_name,
                "status": "rejected",
                "detail": "Not in your store umbrella.",
            })
            continue
        try:
            create_store_user(
                db,
                store_id=sid,
                email=email,
                phone=phone,
                password=password,
                full_name=full_name,
                role=role,
            )
        except UsernameTakenError:
            results.append({
                "store_id": sid,
                "store_name": store_name,
                "status": "skipped",
                "detail": "User already exists at this store.",
            })
            continue
        results.append({
            "store_id": sid,
            "store_name": store_name,
            "status": "created",
            "detail": "",
        })
    return results
