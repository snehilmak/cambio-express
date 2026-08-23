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

Cashiers (employees) hold catalog.read so they can look items up;
catalog management (create/update) needs admin rights. Every
mutation records an operator-audit row (invariant #7).
"""
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
from api.Modules.Catalog.Models import PriceBookItem, Vendor
from api.Modules.Catalog.Requests import (
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
    create_item,
    create_vendor,
    items_query,
    list_vendors,
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
