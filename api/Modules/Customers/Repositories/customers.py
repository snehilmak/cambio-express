"""Customer-directory SQL helpers.

These mirror the existing query shapes used by `find_or_upsert_customer`
and `/api/customers/search` in `app.py`. Each is a thin wrapper around
SQLAlchemy — no policy decisions live here. The Service layer (PR 7)
composes them into the upsert + autocomplete behaviors.

Owner-umbrella scoping is applied via `sibling_store_ids` in EVERY
helper — it's the single point that controls "which stores can a
cashier at store N see customers from?". Solo shops just see their
own row; multi-store owners see one unified list across all locations.
"""
from typing import Iterable

from sqlalchemy import or_
from sqlalchemy.orm import Session

from api.Modules.Customers.Models import Customer, StoreOwnerLink


def sibling_store_ids(db: Session, store_id: int) -> list[int]:
    """All store IDs that share at least one owner with `store_id`.

    Includes `store_id` itself. Returns `[store_id]` when the store has
    no `StoreOwnerLink` rows (solo shop). Mirrors `app.py::sibling_store_ids`.
    """
    owner_ids = [
        r.owner_id for r in
        db.query(StoreOwnerLink).filter(StoreOwnerLink.store_id == store_id).all()
    ]
    if not owner_ids:
        return [store_id]
    sibling_rows = (
        db.query(StoreOwnerLink)
          .filter(StoreOwnerLink.owner_id.in_(owner_ids))
          .all()
    )
    ids = {r.store_id for r in sibling_rows}
    ids.add(store_id)
    return sorted(ids)


def find_by_id_in_stores(
    db: Session, customer_id: int, store_ids: Iterable[int],
) -> Customer | None:
    """Look up a customer by ID, restricted to a set of stores.

    Used by the upsert path to honor an explicit `customer_id` only
    when the target lives inside the caller's owner umbrella — never
    cross-umbrella.
    """
    return (
        db.query(Customer)
          .filter(Customer.id == customer_id, Customer.store_id.in_(store_ids))
          .first()
    )


def find_by_phone_in_stores(
    db: Session, store_ids: Iterable[int],
    phone_country: str, phone_number: str,
) -> Customer | None:
    """Look up a customer by `(phone_country, phone_number)` across a
    set of stores. Empty `phone_number` returns `None` — empty phones
    aren't a valid lookup key (the unique constraint allows multiple
    rows with empty phones because each is a "no phone on file" placeholder)."""
    if not phone_number:
        return None
    return (
        db.query(Customer)
          .filter(
              Customer.store_id.in_(store_ids),
              Customer.phone_country == (phone_country or "+1"),
              Customer.phone_number == phone_number,
          )
          .first()
    )


def search_by_substring(
    db: Session, store_ids: Iterable[int], q: str, *, limit: int = 10,
) -> list[Customer]:
    """ILIKE substring search on `full_name` OR `phone_number`, scoped
    to the given stores, ordered by `updated_at` desc (recent first).

    Returns `[]` for queries shorter than 2 chars — keeps the
    autocomplete from firing on every keystroke.
    """
    if len(q) < 2:
        return []
    like = f"%{q}%"
    return (
        db.query(Customer)
          .filter(Customer.store_id.in_(store_ids))
          .filter(or_(
              Customer.phone_number.ilike(like),
              Customer.full_name.ilike(like),
          ))
          .order_by(Customer.updated_at.desc())
          .limit(limit)
          .all()
    )


def recent_customers(
    db: Session, store_ids: Iterable[int], *, limit: int = 200,
) -> list[Customer]:
    """The N most-recently-updated customers in the umbrella. Used by
    the fuzzy-suggestion path so the SequenceMatcher loop doesn't scan
    the whole directory on every keystroke."""
    return (
        db.query(Customer)
          .filter(Customer.store_id.in_(store_ids))
          .order_by(Customer.updated_at.desc())
          .limit(limit)
          .all()
    )
