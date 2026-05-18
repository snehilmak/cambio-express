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

from sqlalchemy.orm import Session

from api.Modules.Admin.Services.users import (
    UsernameTakenError,
    create_store_user,
)
from api.Modules.Tenancy.Models import Store, StoreOwnerLink, User

VALID_ROLES = {"admin", "employee"}


def bulk_add_user_to_stores(
    db: Session,
    *,
    owner_id: int,
    store_ids: list[int],
    username: str,
    password: str,
    full_name: str = "",
    role: str = "employee",
) -> list[dict]:
    """Create the same User across every requested store that's
    in the owner's umbrella. Returns one result row per
    requested store with one of three statuses:

      ``created``  — new User row inserted
      ``skipped``  — that store already had a user with this username
      ``rejected`` — the store is not in the owner's umbrella

    Caller commits. Per-store failures don't roll the whole
    batch back — each is reported in the response and the
    transaction keeps going (best-effort semantics, matching
    the SPA's "what happened to each one" table view).
    """
    if role not in VALID_ROLES:
        raise ValueError("Role must be 'admin' or 'employee'.")
    if not (username or "").strip():
        raise ValueError("Username is required.")
    if not (password or ""):
        raise ValueError("Password is required.")
    if not store_ids:
        raise ValueError("Pick at least one store.")
    if len(store_ids) > 50:
        # Sanity cap — no umbrella in the wild has 50 stores.
        # Keeps a runaway bulk-create from racing the rate limiter.
        raise ValueError("Cannot target more than 50 stores in one call.")

    allowed = _owner_store_ids(db, owner_id)
    name_lookup = _store_names_by_id(db, list(set(store_ids)))

    results: list[dict] = []
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
                username=username,
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


def _owner_store_ids(db: Session, owner_id: int) -> set[int]:
    rows = (
        db.query(StoreOwnerLink.store_id)
          .filter_by(owner_id=owner_id)
          .all()
    )
    return {sid for (sid,) in rows}


def _store_names_by_id(db: Session, store_ids: list[int]) -> dict[int, str]:
    if not store_ids:
        return {}
    rows = (
        db.query(Store.id, Store.name)
          .filter(Store.id.in_(store_ids))
          .all()
    )
    return {sid: name for sid, name in rows}
