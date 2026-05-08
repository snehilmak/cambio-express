"""Owners module — Controllers (FastAPI router).

Mounts at `/api/v2/owner/*`. First slice ships the locations
list — per-store stats for the multi-store owner umbrella view.

  GET /owner/locations?period=&q= → list owner's stores with
       period-scoped transfer count, volume, over/short, plus
       per-company chips.

Auth: requires JWT principal with role="owner" (or "superadmin"
for support/debug). Subsequent PRs add /owner/dashboard,
/owner/pl-rollup, /owner/store/{id} drill-down, and the
connect/unlink invitation flow.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from api.Core.Database import get_db
from api.Modules.Auth.Controllers import get_principal
from api.Modules.Auth.Models import User
from api.Modules.Owners.Requests import (
    OwnerLocationsResponse,
    OwnerStoreCompanyChip,
    OwnerStoreRow,
)
from api.Modules.Owners.Services import owner_locations_payload


router = APIRouter()


def _require_owner_principal(db: Session, claims: dict) -> User:
    """Resolve the JWT subject to a real User and gate on the owner
    role. Superadmin can hit owner endpoints too — useful for
    support / debug.

    Raises 403 if the role doesn't qualify, 401 if the sub is
    missing or doesn't resolve.
    """
    role = claims.get("role")
    if role not in ("owner", "superadmin"):
        raise HTTPException(
            status_code=403,
            detail="Only multi-store owners can access this resource.",
        )
    sub = claims.get("sub")
    if sub is None:
        raise HTTPException(
            status_code=401,
            detail="JWT is missing the subject claim.",
        )
    user = db.query(User).filter(User.id == int(sub)).one_or_none()
    if user is None:
        raise HTTPException(
            status_code=401,
            detail="JWT subject does not resolve to a user.",
        )
    return user


@router.get("/locations", response_model=OwnerLocationsResponse)
def owner_locations_route(
    period: str = Query("month", pattern="^(today|month|year)$"),
    q: str = Query("", description="Case-insensitive substring on store name"),
    db: Session = Depends(get_db),
    claims: dict = Depends(get_principal),
) -> OwnerLocationsResponse:
    user = _require_owner_principal(db, claims)
    rows, total = owner_locations_payload(db, user, period, q.strip() or None)
    out_rows = [
        OwnerStoreRow(
            store_id=r["store"].id,
            store_name=r["store"].name or "",
            store_slug=r["store"].slug or "",
            transfer_count=r["transfer_count"],
            volume=r["volume"],
            over_short=r["over_short"],
            report_count=r["report_count"],
            companies=[
                OwnerStoreCompanyChip(
                    company=c["company"],
                    count=c["count"],
                    volume=c["volume"],
                )
                for c in r.get("companies", [])
            ],
        )
        for r in rows
    ]
    return OwnerLocationsResponse(
        rows=out_rows, total=total, matched=len(out_rows),
    )
