"""Catalog — Services.

Store-scoped CRUD over the vendor + price-book catalogs. All
lookups pin to ``store_id`` — cross-store access is impossible by
construction. Raise typed errors; the Controllers translate them
to 404/422 so the service layer stays HTTP-free.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Query, Session

from api.Core.Money import to_cents
from api.Modules.Catalog.Models import PriceBookItem, Vendor
from api.Modules.DayClose.Models import Department


class CatalogNotFoundError(Exception):
    pass


class CatalogConflictError(Exception):
    """Duplicate vendor name / item scan code within the store."""


# ── Vendors ────────────────────────────────────────────────


def list_vendors(
    db: Session, store_id: int, *, include_inactive: bool = False,
) -> list[tuple[Vendor, int]]:
    """Vendors with their linked-item counts, name order."""
    q = (
        db.query(Vendor, func.count(PriceBookItem.id))
          .outerjoin(PriceBookItem, PriceBookItem.vendor_id == Vendor.id)
          .filter(Vendor.store_id == store_id)
    )
    if not include_inactive:
        q = q.filter(Vendor.is_active.is_(True))
    return q.group_by(Vendor.id).order_by(Vendor.name).all()


def _vendor_name_taken(
    db: Session, store_id: int, name: str, *, exclude_id: int | None = None,
) -> bool:
    q = db.query(Vendor.id).filter(
        Vendor.store_id == store_id,
        func.lower(Vendor.name) == name.lower(),
    )
    if exclude_id is not None:
        q = q.filter(Vendor.id != exclude_id)
    return q.first() is not None


def create_vendor(db: Session, store_id: int, fields: dict[str, Any]) -> Vendor:
    name = str(fields["name"]).strip()
    if not name:
        raise CatalogConflictError("Vendor name is required.")
    if _vendor_name_taken(db, store_id, name):
        raise CatalogConflictError(f'A vendor named "{name}" already exists.')
    vendor = Vendor(
        store_id=store_id,
        name=name,
        contact_name=str(fields.get("contact_name") or "").strip(),
        phone=str(fields.get("phone") or "").strip(),
        email=str(fields.get("email") or "").strip(),
        account_number=str(fields.get("account_number") or "").strip(),
        notes=str(fields.get("notes") or "").strip(),
    )
    db.add(vendor)
    db.flush()
    return vendor


def update_vendor(
    db: Session, store_id: int, vendor_id: int, changes: dict[str, Any],
) -> Vendor:
    vendor = (
        db.query(Vendor)
          .filter_by(id=vendor_id, store_id=store_id)
          .first()
    )
    if vendor is None:
        raise CatalogNotFoundError("Vendor not found.")
    if "name" in changes and changes["name"] is not None:
        name = str(changes["name"]).strip()
        if not name:
            raise CatalogConflictError("Vendor name is required.")
        if _vendor_name_taken(db, store_id, name, exclude_id=vendor.id):
            raise CatalogConflictError(
                f'A vendor named "{name}" already exists.'
            )
        vendor.name = name
    for field in ("contact_name", "phone", "email", "account_number", "notes"):
        if field in changes and changes[field] is not None:
            setattr(vendor, field, str(changes[field]).strip())
    if changes.get("is_active") is not None:
        vendor.is_active = bool(changes["is_active"])
    db.flush()
    return vendor


# ── Price-book items ───────────────────────────────────────


def items_query(
    db: Session,
    store_id: int,
    *,
    q: str = "",
    department_id: int | None = None,
    vendor_id: int | None = None,
    include_inactive: bool = False,
) -> Query:
    """Filtered item query for the shared ``paginate()`` helper.
    Search matches name substring OR scan-code prefix — the two
    ways an operator actually looks an item up."""
    query = (
        db.query(PriceBookItem)
          .filter(PriceBookItem.store_id == store_id)
    )
    needle = q.strip()
    if needle:
        query = query.filter(
            PriceBookItem.name.ilike(f"%{needle}%")
            | PriceBookItem.pos_code.like(f"{needle}%")
        )
    if department_id is not None:
        query = query.filter(PriceBookItem.department_id == department_id)
    if vendor_id is not None:
        query = query.filter(PriceBookItem.vendor_id == vendor_id)
    if not include_inactive:
        query = query.filter(PriceBookItem.is_active.is_(True))
    return query.order_by(PriceBookItem.name, PriceBookItem.id)


def _pos_code_taken(
    db: Session, store_id: int, pos_code: str, *,
    exclude_id: int | None = None,
) -> bool:
    q = db.query(PriceBookItem.id).filter_by(
        store_id=store_id, pos_code=pos_code,
    )
    if exclude_id is not None:
        q = q.filter(PriceBookItem.id != exclude_id)
    return q.first() is not None


def _resolve_department(
    db: Session, store_id: int, department_id: int | None,
) -> int | None:
    if department_id is None:
        return None
    dept = (
        db.query(Department)
          .filter_by(id=department_id, store_id=store_id)
          .first()
    )
    if dept is None:
        raise CatalogNotFoundError("Department not found.")
    return dept.id


def _resolve_vendor(
    db: Session, store_id: int, vendor_id: int | None,
) -> int | None:
    if vendor_id is None:
        return None
    vendor = (
        db.query(Vendor)
          .filter_by(id=vendor_id, store_id=store_id)
          .first()
    )
    if vendor is None:
        raise CatalogNotFoundError("Vendor not found.")
    return vendor.id


def create_item(
    db: Session, store_id: int, fields: dict[str, Any], *,
    source: str = "manual",
) -> PriceBookItem:
    pos_code = str(fields["pos_code"]).strip()
    if not pos_code:
        raise CatalogConflictError("Scan code is required.")
    if _pos_code_taken(db, store_id, pos_code):
        raise CatalogConflictError(
            f'An item with scan code "{pos_code}" already exists.'
        )
    item = PriceBookItem(
        store_id=store_id,
        pos_code=pos_code,
        pos_code_format=str(fields.get("pos_code_format") or "upc"),
        name=str(fields["name"]).strip(),
        department_id=_resolve_department(
            db, store_id, fields.get("department_id"),
        ),
        vendor_id=_resolve_vendor(db, store_id, fields.get("vendor_id")),
        price_cents=to_cents(fields.get("price") or 0),
        cost_cents=to_cents(fields.get("cost") or 0),
        is_taxable=bool(fields.get("is_taxable", True)),
        source=source,
    )
    db.add(item)
    db.flush()
    return item


def update_item(
    db: Session, store_id: int, item_id: int, changes: dict[str, Any],
) -> PriceBookItem:
    item = (
        db.query(PriceBookItem)
          .filter_by(id=item_id, store_id=store_id)
          .first()
    )
    if item is None:
        raise CatalogNotFoundError("Item not found.")
    if changes.get("pos_code") is not None:
        pos_code = str(changes["pos_code"]).strip()
        if not pos_code:
            raise CatalogConflictError("Scan code is required.")
        if _pos_code_taken(db, store_id, pos_code, exclude_id=item.id):
            raise CatalogConflictError(
                f'An item with scan code "{pos_code}" already exists.'
            )
        item.pos_code = pos_code
    if changes.get("pos_code_format") is not None:
        item.pos_code_format = str(changes["pos_code_format"])
    if changes.get("name") is not None:
        item.name = str(changes["name"]).strip()
    # 0 = explicit "clear the link" (None means leave unchanged —
    # see ItemUpdateRequest).
    if changes.get("department_id") is not None:
        did = int(changes["department_id"])
        item.department_id = (
            None if did == 0 else _resolve_department(db, store_id, did)
        )
    if changes.get("vendor_id") is not None:
        vid = int(changes["vendor_id"])
        item.vendor_id = (
            None if vid == 0 else _resolve_vendor(db, store_id, vid)
        )
    if changes.get("price") is not None:
        item.price_cents = to_cents(changes["price"])
    if changes.get("cost") is not None:
        item.cost_cents = to_cents(changes["cost"])
    if changes.get("is_taxable") is not None:
        item.is_taxable = bool(changes["is_taxable"])
    if changes.get("is_active") is not None:
        item.is_active = bool(changes["is_active"])
    db.flush()
    return item


__all__ = [
    "CatalogConflictError",
    "CatalogNotFoundError",
    "create_item",
    "create_vendor",
    "items_query",
    "list_vendors",
    "update_item",
    "update_vendor",
]
