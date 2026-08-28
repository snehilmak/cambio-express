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
from api.Modules.Catalog.Models import (
    INVOICE_STATUSES,
    PriceBookItem,
    PurchaseInvoice,
    PurchaseInvoiceLine,
    Vendor,
)
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
        item_number=str(fields.get("item_number") or "").strip(),
        size=str(fields.get("size") or "").strip(),
        case_size=(
            int(fields["case_size"])
            if fields.get("case_size") else None
        ),
        case_cost_cents=(
            to_cents(fields["case_cost"])
            if fields.get("case_cost") is not None else None
        ),
        is_ebt=bool(fields.get("is_ebt", False)),
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
    if changes.get("item_number") is not None:
        item.item_number = str(changes["item_number"]).strip()
    if changes.get("size") is not None:
        item.size = str(changes["size"]).strip()
    # 0 = explicit clear for the nullable case fields (None = leave
    # unchanged) — same sentinel as the optional FKs above.
    if changes.get("case_size") is not None:
        cs = int(changes["case_size"])
        item.case_size = None if cs == 0 else cs
    if changes.get("case_cost") is not None:
        cc = float(changes["case_cost"])
        item.case_cost_cents = None if cc == 0 else to_cents(cc)
    if changes.get("is_ebt") is not None:
        item.is_ebt = bool(changes["is_ebt"])
    db.flush()
    return item


# ── Purchase invoices ──────────────────────────────────────


def invoices_query(
    db: Session,
    store_id: int,
    *,
    vendor_id: int | None = None,
    status: str | None = None,
    q: str = "",
) -> Query:
    """Filtered invoice query for the shared ``paginate()`` helper,
    newest invoice date first."""
    query = (
        db.query(PurchaseInvoice)
          .filter(PurchaseInvoice.store_id == store_id)
    )
    if vendor_id is not None:
        query = query.filter(PurchaseInvoice.vendor_id == vendor_id)
    if status is not None:
        query = query.filter(PurchaseInvoice.status == status)
    needle = q.strip()
    if needle:
        query = query.filter(
            PurchaseInvoice.invoice_number.ilike(f"%{needle}%")
        )
    return query.order_by(
        PurchaseInvoice.invoice_date.desc(), PurchaseInvoice.id.desc(),
    )


def _invoice_number_taken(
    db: Session, store_id: int, vendor_id: int, invoice_number: str, *,
    exclude_id: int | None = None,
) -> bool:
    q = db.query(PurchaseInvoice.id).filter_by(
        store_id=store_id, vendor_id=vendor_id,
        invoice_number=invoice_number,
    )
    if exclude_id is not None:
        q = q.filter(PurchaseInvoice.id != exclude_id)
    return q.first() is not None


def _resolve_item(db: Session, store_id: int, item_id: int) -> int:
    item = (
        db.query(PriceBookItem)
          .filter_by(id=item_id, store_id=store_id)
          .first()
    )
    if item is None:
        raise CatalogNotFoundError("Item not found.")
    return item.id


def _build_lines(
    db: Session, store_id: int, lines: list[dict[str, Any]],
) -> list[PurchaseInvoiceLine]:
    out: list[PurchaseInvoiceLine] = []
    for line in lines:
        item_id = line.get("item_id")
        if item_id is not None:
            item_id = _resolve_item(db, store_id, int(item_id))
        quantity = float(line.get("quantity") or 1.0)
        unit_cost_cents = to_cents(line.get("unit_cost") or 0)
        line_total = line.get("line_total")
        # The printed extended amount wins when keyed; otherwise
        # derive it from quantity × unit cost.
        line_total_cents = (
            to_cents(line_total) if line_total is not None
            else round(quantity * unit_cost_cents)
        )
        out.append(PurchaseInvoiceLine(
            store_id=store_id,
            item_id=item_id,
            description=str(line.get("description") or "").strip(),
            quantity=quantity,
            unit_cost_cents=unit_cost_cents,
            line_total_cents=line_total_cents,
        ))
    return out


def _apply_line_costs_to_items(
    db: Session, store_id: int, lines: list[PurchaseInvoiceLine],
) -> int:
    """Push each linked line's unit cost onto its price-book item —
    the Modisoft-parity 'invoice updates my costs' feature. Last
    line wins per item; returns how many items changed."""
    updated = 0
    for line in lines:
        if line.item_id is None or not line.unit_cost_cents:
            continue
        item = db.get(PriceBookItem, line.item_id)
        if item is None or item.store_id != store_id:
            continue
        if int(item.cost_cents or 0) != int(line.unit_cost_cents):
            item.cost_cents = int(line.unit_cost_cents)
            updated += 1
    return updated


def create_invoice(
    db: Session, store_id: int, fields: dict[str, Any], *,
    created_by: int | None,
) -> tuple[PurchaseInvoice, int]:
    """Create an invoice (+ lines). Returns (invoice,
    items_cost_updated) — the second element is 0 unless
    ``update_item_costs`` was set."""
    vendor_id = _resolve_vendor(db, store_id, int(fields["vendor_id"]))
    assert vendor_id is not None  # required field, resolver raises
    invoice_number = str(fields["invoice_number"]).strip()
    if not invoice_number:
        raise CatalogConflictError("Invoice number is required.")
    if _invoice_number_taken(db, store_id, vendor_id, invoice_number):
        raise CatalogConflictError(
            f'Invoice "{invoice_number}" already exists for this vendor.'
        )
    status = str(fields.get("status") or "open")
    if status not in INVOICE_STATUSES:
        raise CatalogConflictError("Unknown invoice status.")
    invoice = PurchaseInvoice(
        store_id=store_id,
        vendor_id=vendor_id,
        invoice_number=invoice_number,
        invoice_date=fields["invoice_date"],
        due_date=fields.get("due_date"),
        subtotal_cents=to_cents(fields.get("subtotal") or 0),
        tax_cents=to_cents(fields.get("tax") or 0),
        other_cents=to_cents(fields.get("other") or 0),
        status=status,
        paid_on=fields.get("paid_on"),
        notes=str(fields.get("notes") or "").strip(),
        created_by=created_by,
    )
    invoice.lines = _build_lines(db, store_id, fields.get("lines") or [])
    db.add(invoice)
    db.flush()
    updated = 0
    if fields.get("update_item_costs"):
        updated = _apply_line_costs_to_items(db, store_id, invoice.lines)
    return invoice, updated


def update_invoice(
    db: Session, store_id: int, invoice_id: int,
    changes: dict[str, Any],
) -> tuple[PurchaseInvoice, int]:
    """PATCH-style update. ``lines`` replaces the full set when
    present. Returns (invoice, items_cost_updated)."""
    invoice = (
        db.query(PurchaseInvoice)
          .filter_by(id=invoice_id, store_id=store_id)
          .first()
    )
    if invoice is None:
        raise CatalogNotFoundError("Invoice not found.")
    if changes.get("vendor_id") is not None:
        invoice.vendor_id = _resolve_vendor(
            db, store_id, int(changes["vendor_id"]),
        )
    if changes.get("invoice_number") is not None:
        number = str(changes["invoice_number"]).strip()
        if not number:
            raise CatalogConflictError("Invoice number is required.")
        if _invoice_number_taken(
            db, store_id, int(invoice.vendor_id), number,
            exclude_id=invoice.id,
        ):
            raise CatalogConflictError(
                f'Invoice "{number}" already exists for this vendor.'
            )
        invoice.invoice_number = number
    if changes.get("invoice_date") is not None:
        invoice.invoice_date = changes["invoice_date"]
    if "due_date" in changes:
        invoice.due_date = changes["due_date"]
    for money_field in ("subtotal", "tax", "other"):
        if changes.get(money_field) is not None:
            setattr(
                invoice, f"{money_field}_cents",
                to_cents(changes[money_field]),
            )
    if changes.get("status") is not None:
        status = str(changes["status"])
        if status not in INVOICE_STATUSES:
            raise CatalogConflictError("Unknown invoice status.")
        invoice.status = status
        if status != "paid":
            invoice.paid_on = None
    if "paid_on" in changes and changes["paid_on"] is not None:
        invoice.paid_on = changes["paid_on"]
    if changes.get("notes") is not None:
        invoice.notes = str(changes["notes"]).strip()
    if changes.get("lines") is not None:
        invoice.lines = _build_lines(db, store_id, changes["lines"])
    db.flush()
    updated = 0
    if changes.get("update_item_costs"):
        updated = _apply_line_costs_to_items(db, store_id, invoice.lines)
    return invoice, updated


def delete_invoice(
    db: Session, store_id: int, invoice_id: int,
) -> PurchaseInvoice:
    invoice = (
        db.query(PurchaseInvoice)
          .filter_by(id=invoice_id, store_id=store_id)
          .first()
    )
    if invoice is None:
        raise CatalogNotFoundError("Invoice not found.")
    db.delete(invoice)
    db.flush()
    return invoice


__all__ = [
    "CatalogConflictError",
    "CatalogNotFoundError",
    "create_invoice",
    "create_item",
    "create_vendor",
    "delete_invoice",
    "invoices_query",
    "items_query",
    "list_vendors",
    "update_invoice",
    "update_item",
    "update_vendor",
]
