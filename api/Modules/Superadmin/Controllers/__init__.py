"""Superadmin module — Controllers (FastAPI router).

Mounts at `/api/v2/superadmin/*`. First slice ships the
platform-wide stores list — the superadmin's primary workflow.

  GET /superadmin/stores → list every store with plan, trial
       state, retention timer, and Stripe linkage.

Auth: requires JWT principal with role="superadmin". Subsequent
PRs add the controls dashboard, anomaly feed, audit log feed,
discounts/announcements/feature-flag CRUD, and impersonation.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from api.Core.Database import get_db
from api.Modules.Auth.Controllers import get_principal
from api.Modules.Superadmin.Requests import (
    SuperadminStoreListResponse,
    SuperadminStoreRow,
)


router = APIRouter()


def _require_superadmin(claims: dict) -> None:
    if claims.get("role") != "superadmin":
        raise HTTPException(
            status_code=403,
            detail="Superadmin scope required.",
        )


def _iso(dt) -> str:
    return dt.isoformat() if dt else ""


@router.get("/stores", response_model=SuperadminStoreListResponse)
def list_stores_route(
    db: Session = Depends(get_db),
    claims: dict = Depends(get_principal),
) -> SuperadminStoreListResponse:
    _require_superadmin(claims)
    from app import Store
    stores = db.query(Store).order_by(Store.created_at.desc()).all()
    rows = [
        SuperadminStoreRow(
            store_id=s.id,
            name=s.name or "",
            slug=s.slug or "",
            email=s.email or "",
            phone=s.phone or "",
            plan=s.plan or "trial",
            billing_cycle=s.billing_cycle or "",
            is_active=bool(s.is_active),
            created_at=_iso(s.created_at),
            trial_ends_at=_iso(s.trial_ends_at),
            grace_ends_at=_iso(s.grace_ends_at),
            data_retention_until=_iso(s.data_retention_until),
            stripe_customer_id=s.stripe_customer_id or "",
            stripe_subscription_id=s.stripe_subscription_id or "",
        )
        for s in stores
    ]
    return SuperadminStoreListResponse(rows=rows, total=len(rows))
