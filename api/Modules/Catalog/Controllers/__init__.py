"""Catalog module — Controllers (FastAPI router).

Mounts at `/api/v2/catalog/*`:

  GET  /vendors                  list vendors (?include_inactive=1)
  POST /vendors                  create vendor
  PUT  /vendors/{id}             update vendor / deactivate
  GET  /items                    paginated + searchable item list
                                 (?q=&department_id=&vendor_id=
                                  &include_inactive=1&page=&per_page=)
  POST /items                    create item
  PUT  /items/{id}               update item / deactivate
  GET  /invoices                 paginated invoice list
                                 (?q=&vendor_id=&status=)
  GET  /invoices/{id}            invoice detail with lines
  POST /invoices                 create invoice (+ optional
                                 update_item_costs feedback)
  PUT  /invoices/{id}            update invoice / replace lines
  DELETE /invoices/{id}          delete invoice

Cashiers (employees) hold catalog.read so they can look items up;
catalog management (create/update) needs admin rights. Every
mutation records an operator-audit row (invariant #7).
"""
from datetime import date, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from sqlalchemy.orm import Session

from api.Core.Database import get_db
from api.Core.Pagination import PaginationParams, paginate, pagination_dep
from api.Modules.Auth.Controllers import get_principal
from api.Modules.Auth.Services.principal import (
    require_permission,
    resolve_store_scope,
)
from api.Modules.Catalog.Models import (
    PriceBookItem,
    PurchaseInvoice,
    Vendor,
)
from api.Modules.Catalog.Requests import (
    InvoiceDetail,
    InvoiceLineRow,
    InvoiceListResponse,
    InvoiceResponse,
    InvoiceRow,
    InvoiceUpdateRequest,
    InvoiceWriteRequest,
    ItemListResponse,
    ItemResponse,
    ItemRow,
    ItemUpdateRequest,
    ItemWriteRequest,
    VendorListResponse,
    VendorResponse,
    VendorRow,
    VendorUpdateRequest,
    VendorWriteRequest,
)
from api.Modules.Catalog.Services import (
    CatalogConflictError,
    CatalogNotFoundError,
    create_invoice,
    create_item,
    create_vendor,
    delete_invoice,
    invoices_query,
    items_query,
    list_vendors,
    update_invoice,
    update_item,
    update_vendor,
)

router = APIRouter(prefix="/catalog", tags=["catalog"])


def _audit(
    db: Session, *, claims: dict[str, Any], action: str,
    target_type: str, target_id: str, summary: str,
) -> None:
    """Operator-audit emitter — CLAUDE.md invariant #7."""
    from api.Modules.Audit.Services import record_operator_action
    record_operator_action(
        db,
        store_id=int(claims["store_id"]),
        user_id=int(claims["sub"]),
        user_name=claims.get("name") or claims.get("username") or "",
        user_role=claims.get("role") or "",
        target_type=target_type,
        action=action,
        target_id=target_id,
        summary=summary[:255],
    )


def _vendor_row(v: Vendor, item_count: int) -> VendorRow:
    return VendorRow(
        id=v.id, name=v.name or "",
        contact_name=v.contact_name or "",
        phone=v.phone or "", email=v.email or "",
        account_number=v.account_number or "",
        notes=v.notes or "",
        is_active=bool(v.is_active),
        item_count=item_count,
    )


def _item_row(i: PriceBookItem) -> ItemRow:
    return ItemRow(
        id=i.id,
        pos_code=i.pos_code or "",
        pos_code_format=i.pos_code_format or "upc",
        name=i.name or "",
        department_id=i.department_id,
        department_name=(i.department.name or "") if i.department else "",
        vendor_id=i.vendor_id,
        vendor_name=(i.vendor.name or "") if i.vendor else "",
        price=i.price,
        cost=i.cost,
        is_taxable=bool(i.is_taxable),
        is_active=bool(i.is_active),
        source=i.source or "manual",
        item_number=i.item_number or "",
        size=i.size or "",
        case_size=i.case_size,
        # Read the cents column directly: the DollarView maps NULL
        # to 0.0, but the API contract wants null = "not tracked".
        case_cost=(
            None if i.case_cost_cents is None
            else i.case_cost_cents / 100.0
        ),
        is_ebt=bool(i.is_ebt),
    )


# ── Vendors ────────────────────────────────────────────────


@router.get("/vendors", response_model=VendorListResponse)
def list_vendors_route(
    include_inactive: bool = Query(False),
    db: Session = Depends(get_db),
    claims: dict[str, Any] = Depends(get_principal),
) -> VendorListResponse:
    sid = resolve_store_scope(claims)
    require_permission(claims, "catalog", "read")
    return VendorListResponse(
        vendors=[
            _vendor_row(v, count)
            for v, count in list_vendors(
                db, sid, include_inactive=include_inactive,
            )
        ],
    )


@router.post("/vendors", response_model=VendorResponse, status_code=201)
def create_vendor_route(
    body: VendorWriteRequest,
    db: Session = Depends(get_db),
    claims: dict[str, Any] = Depends(get_principal),
) -> VendorResponse:
    sid = resolve_store_scope(claims)
    require_permission(claims, "catalog", "update")
    try:
        vendor = create_vendor(db, sid, body.model_dump())
    except CatalogConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    _audit(
        db, claims=claims, action="create_vendor",
        target_type="vendor", target_id=str(vendor.id),
        summary=f"vendor {vendor.name}",
    )
    db.commit()
    return VendorResponse(vendor=_vendor_row(vendor, 0))


@router.put("/vendors/{vendor_id}", response_model=VendorResponse)
def update_vendor_route(
    vendor_id: int = Path(..., ge=1),
    body: VendorUpdateRequest = ...,
    db: Session = Depends(get_db),
    claims: dict[str, Any] = Depends(get_principal),
) -> VendorResponse:
    sid = resolve_store_scope(claims)
    require_permission(claims, "catalog", "update")
    try:
        vendor = update_vendor(db, sid, vendor_id, body.model_dump())
    except CatalogNotFoundError:
        raise HTTPException(status_code=404, detail="Vendor not found")
    except CatalogConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    from sqlalchemy import func
    item_count = (
        db.query(func.count(PriceBookItem.id))
          .filter(PriceBookItem.vendor_id == vendor.id)
          .scalar()
    ) or 0
    _audit(
        db, claims=claims, action="update_vendor",
        target_type="vendor", target_id=str(vendor.id),
        summary=f"vendor {vendor.name} updated",
    )
    db.commit()
    return VendorResponse(vendor=_vendor_row(vendor, int(item_count)))


# ── Price-book items ───────────────────────────────────────


@router.get("/items", response_model=ItemListResponse)
def list_items_route(
    q: str = Query("", max_length=160),
    department_id: int | None = Query(None, ge=1),
    vendor_id: int | None = Query(None, ge=1),
    include_inactive: bool = Query(False),
    pagination: PaginationParams = Depends(pagination_dep),
    db: Session = Depends(get_db),
    claims: dict[str, Any] = Depends(get_principal),
) -> ItemListResponse:
    sid = resolve_store_scope(claims)
    require_permission(claims, "catalog", "read")
    query = items_query(
        db, sid, q=q, department_id=department_id,
        vendor_id=vendor_id, include_inactive=include_inactive,
    )
    payload = paginate(query, pagination, adapter=_item_row)
    return ItemListResponse(
        rows=payload["rows"],
        total=payload["total"],
        page=payload["page"],
        total_pages=payload["total_pages"],
    )


@router.post("/items", response_model=ItemResponse, status_code=201)
def create_item_route(
    body: ItemWriteRequest,
    db: Session = Depends(get_db),
    claims: dict[str, Any] = Depends(get_principal),
) -> ItemResponse:
    sid = resolve_store_scope(claims)
    require_permission(claims, "catalog", "update")
    try:
        item = create_item(db, sid, body.model_dump())
    except CatalogNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except CatalogConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    _audit(
        db, claims=claims, action="create_price_book_item",
        target_type="price_book_item", target_id=str(item.id),
        summary=f"item {item.pos_code} {item.name} ${item.price:,.2f}",
    )
    db.commit()
    return ItemResponse(item=_item_row(item))


@router.put("/items/{item_id}", response_model=ItemResponse)
def update_item_route(
    item_id: int = Path(..., ge=1),
    body: ItemUpdateRequest = ...,
    db: Session = Depends(get_db),
    claims: dict[str, Any] = Depends(get_principal),
) -> ItemResponse:
    sid = resolve_store_scope(claims)
    require_permission(claims, "catalog", "update")
    try:
        item = update_item(db, sid, item_id, body.model_dump())
    except CatalogNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except CatalogConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    _audit(
        db, claims=claims, action="update_price_book_item",
        target_type="price_book_item", target_id=str(item.id),
        summary=f"item {item.pos_code} {item.name} updated",
    )
    db.commit()
    return ItemResponse(item=_item_row(item))


# ── Purchase invoices ──────────────────────────────────────


def _parse_date(raw: str, field: str) -> date:
    try:
        return datetime.strptime(raw, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(
            status_code=422,
            detail={"field": field, "message": "Use YYYY-MM-DD."},
        )


def _invoice_row(inv: PurchaseInvoice, *, with_lines: bool = False):
    base = dict(
        id=inv.id,
        vendor_id=int(inv.vendor_id),
        vendor_name=(inv.vendor.name or "") if inv.vendor else "",
        invoice_number=inv.invoice_number or "",
        invoice_date=inv.invoice_date.isoformat(),
        due_date=inv.due_date.isoformat() if inv.due_date else None,
        subtotal=inv.subtotal,
        tax=inv.tax,
        other=inv.other,
        total=inv.total_cents / 100.0,
        status=inv.status or "open",
        paid_on=inv.paid_on.isoformat() if inv.paid_on else None,
        notes=inv.notes or "",
        line_count=len(inv.lines),
    )
    if not with_lines:
        return InvoiceRow(**base)
    return InvoiceDetail(
        **base,
        lines=[
            InvoiceLineRow(
                id=line.id,
                item_id=line.item_id,
                item_name=(line.item.name or "") if line.item else "",
                description=line.description or "",
                quantity=float(line.quantity or 0),
                unit_cost=line.unit_cost,
                line_total=line.line_total,
            )
            for line in inv.lines
        ],
    )


def _invoice_dates_or_422(body) -> dict:
    """Convert the request's YYYY-MM-DD strings to date objects,
    dropping unset fields so the Service's PATCH semantics hold."""
    out = body.model_dump(exclude_unset=False)
    if out.get("invoice_date") is not None:
        out["invoice_date"] = _parse_date(out["invoice_date"], "invoice_date")
    if out.get("due_date") is not None:
        out["due_date"] = _parse_date(out["due_date"], "due_date")
    elif not getattr(body, "clear_due_date", False):
        out.pop("due_date", None)
    out.pop("clear_due_date", None)
    if out.get("paid_on") is not None:
        out["paid_on"] = _parse_date(out["paid_on"], "paid_on")
    if out.get("lines") is not None:
        out["lines"] = [dict(line) for line in out["lines"]]
    return out


@router.get("/invoices", response_model=InvoiceListResponse)
def list_invoices_route(
    q: str = Query("", max_length=60),
    vendor_id: int | None = Query(None, ge=1),
    status: str | None = Query(None, pattern="^(open|paid)$"),
    pagination: PaginationParams = Depends(pagination_dep),
    db: Session = Depends(get_db),
    claims: dict[str, Any] = Depends(get_principal),
) -> InvoiceListResponse:
    sid = resolve_store_scope(claims)
    require_permission(claims, "catalog", "read")
    payload = paginate(
        invoices_query(db, sid, vendor_id=vendor_id, status=status, q=q),
        pagination,
        adapter=_invoice_row,
    )
    return InvoiceListResponse(
        rows=payload["rows"],
        total=payload["total"],
        page=payload["page"],
        total_pages=payload["total_pages"],
    )


@router.get("/invoices/{invoice_id}", response_model=InvoiceResponse)
def get_invoice_route(
    invoice_id: int = Path(..., ge=1),
    db: Session = Depends(get_db),
    claims: dict[str, Any] = Depends(get_principal),
) -> InvoiceResponse:
    sid = resolve_store_scope(claims)
    require_permission(claims, "catalog", "read")
    invoice = (
        db.query(PurchaseInvoice)
          .filter_by(id=invoice_id, store_id=sid)
          .first()
    )
    if invoice is None:
        raise HTTPException(status_code=404, detail="Invoice not found")
    return InvoiceResponse(
        invoice=_invoice_row(invoice, with_lines=True),
        items_cost_updated=0,
    )


@router.post("/invoices", response_model=InvoiceResponse, status_code=201)
def create_invoice_route(
    body: InvoiceWriteRequest,
    db: Session = Depends(get_db),
    claims: dict[str, Any] = Depends(get_principal),
) -> InvoiceResponse:
    sid = resolve_store_scope(claims)
    require_permission(claims, "catalog", "update")
    try:
        invoice, updated = create_invoice(
            db, sid, _invoice_dates_or_422(body),
            created_by=int(claims["sub"]),
        )
    except CatalogNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except CatalogConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    _audit(
        db, claims=claims, action="create_purchase_invoice",
        target_type="purchase_invoice", target_id=str(invoice.id),
        summary=(
            f"invoice {invoice.invoice_number} "
            f"({(invoice.vendor.name or '') if invoice.vendor else ''}) "
            f"${invoice.total_cents / 100.0:,.2f}"
        ),
    )
    db.commit()
    return InvoiceResponse(
        invoice=_invoice_row(invoice, with_lines=True),
        items_cost_updated=updated,
    )


@router.put("/invoices/{invoice_id}", response_model=InvoiceResponse)
def update_invoice_route(
    invoice_id: int = Path(..., ge=1),
    body: InvoiceUpdateRequest = ...,
    db: Session = Depends(get_db),
    claims: dict[str, Any] = Depends(get_principal),
) -> InvoiceResponse:
    sid = resolve_store_scope(claims)
    require_permission(claims, "catalog", "update")
    try:
        invoice, updated = update_invoice(
            db, sid, invoice_id, _invoice_dates_or_422(body),
        )
    except CatalogNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except CatalogConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    _audit(
        db, claims=claims, action="update_purchase_invoice",
        target_type="purchase_invoice", target_id=str(invoice.id),
        summary=f"invoice {invoice.invoice_number} updated",
    )
    db.commit()
    return InvoiceResponse(
        invoice=_invoice_row(invoice, with_lines=True),
        items_cost_updated=updated,
    )


@router.delete("/invoices/{invoice_id}")
def delete_invoice_route(
    invoice_id: int = Path(..., ge=1),
    db: Session = Depends(get_db),
    claims: dict[str, Any] = Depends(get_principal),
) -> dict:
    sid = resolve_store_scope(claims)
    require_permission(claims, "catalog", "update")
    try:
        invoice = delete_invoice(db, sid, invoice_id)
    except CatalogNotFoundError:
        raise HTTPException(status_code=404, detail="Invoice not found")
    _audit(
        db, claims=claims, action="delete_purchase_invoice",
        target_type="purchase_invoice", target_id=str(invoice_id),
        summary=f"invoice {invoice.invoice_number} deleted",
    )
    db.commit()
    return {"ok": True}
