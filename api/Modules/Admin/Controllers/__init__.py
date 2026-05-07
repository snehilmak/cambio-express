"""Admin module — Controllers (FastAPI router).

Mounts at `/api/v2/admin/*`. Endpoints:

  GET /admin/store-info → the JWT principal's store row
  PUT /admin/store-info → update editable fields

JWT-required, scoped to the principal's store. Superadmin (no
store scope) → 403.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from api.Core.Database import get_db
from api.Modules.Auth.Controllers import get_principal
from api.Modules.Admin.Repositories import find_store
from api.Modules.Admin.Requests import (
    StoreInfoResponse,
    StoreInfoRow,
    StoreInfoUpdateRequest,
)
from api.Modules.Admin.Services import update_store_info


router = APIRouter()


def _require_store(claims: dict) -> int:
    sid = claims.get("store_id")
    if sid is None:
        raise HTTPException(
            status_code=403,
            detail=(
                "JWT does not carry a store scope. Sign in as a "
                "store admin or owner to manage settings."
            ),
        )
    return int(sid)


def _to_row(s) -> StoreInfoRow:
    return StoreInfoRow(
        id=s.id,
        name=s.name or "",
        slug=s.slug or "",
        email=s.email or "",
        phone=s.phone or "",
        address=s.address or "",
        plan=s.plan or "trial",
        federal_tax_rate=float(s.federal_tax_rate or 0),
        is_active=bool(s.is_active),
    )


@router.get("/store-info", response_model=StoreInfoResponse)
def get_store_info(
    db: Session = Depends(get_db),
    claims: dict = Depends(get_principal),
) -> StoreInfoResponse:
    store_id = _require_store(claims)
    store = find_store(db, store_id)
    if store is None:
        raise HTTPException(status_code=404, detail="Store not found")
    return StoreInfoResponse(store=_to_row(store))


@router.put("/store-info", response_model=StoreInfoResponse)
def update_store_info_route(
    body: StoreInfoUpdateRequest,
    db: Session = Depends(get_db),
    claims: dict = Depends(get_principal),
) -> StoreInfoResponse:
    """Update operator-editable store fields. Only the role
    `admin` (or superadmin / owner) is allowed — the legacy
    settings page is gated by `admin_required`. Cashiers
    (role `employee`) hitting this endpoint return 403."""
    if claims.get("role") not in ("admin", "owner", "superadmin"):
        raise HTTPException(
            status_code=403,
            detail="Only store admins can update store info",
        )
    store_id = _require_store(claims)
    store = find_store(db, store_id)
    if store is None:
        raise HTTPException(status_code=404, detail="Store not found")
    fields = body.model_dump(exclude_unset=True)
    try:
        update_store_info(db, store, fields)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    db.commit()
    return StoreInfoResponse(store=_to_row(store))
