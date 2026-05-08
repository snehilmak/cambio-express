"""Superadmin module — Controllers (FastAPI router).

Mounts at `/api/v2/superadmin/*`. Endpoints:

  GET /superadmin/stores      → list every store with plan, trial
       state, retention timer, and Stripe linkage.
  GET /superadmin/audit-log   → paginated platform-wide audit log
       (every superadmin mutation, with actor + target).

Auth: requires JWT principal with role="superadmin". Subsequent
PRs add the controls dashboard, anomaly feed, discounts/
announcements/feature-flag CRUD, and impersonation.
"""
from math import ceil

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from api.Core.Database import get_db
from api.Modules.Auth.Controllers import get_principal
from api.Modules.Superadmin.Requests import (
    SuperadminAuditListResponse,
    SuperadminAuditRow,
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


@router.get("/audit-log", response_model=SuperadminAuditListResponse)
def list_audit_route(
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    action: str = Query("", description="Optional substring filter on action"),
    db: Session = Depends(get_db),
    claims: dict = Depends(get_principal),
) -> SuperadminAuditListResponse:
    """Paginated platform-wide audit log. Newest entries first.
    `action` is a case-insensitive substring filter so the
    superadmin can drill into a specific event type (e.g. "trial",
    "comp_plan", "feature_toggle"). The legacy report at
    `/superadmin/reports/audit-log` covers the same data; this
    endpoint feeds the SPA equivalent."""
    _require_superadmin(claims)
    from app import SuperadminAuditLog
    q = db.query(SuperadminAuditLog)
    if action:
        q = q.filter(SuperadminAuditLog.action.ilike(f"%{action}%"))
    total = q.count()
    rows = (
        q.order_by(SuperadminAuditLog.created_at.desc())
         .offset((page - 1) * per_page)
         .limit(per_page)
         .all()
    )
    return SuperadminAuditListResponse(
        rows=[
            SuperadminAuditRow(
                id=r.id,
                admin_id=r.admin_id,
                admin_name=r.admin_name or "",
                action=r.action or "",
                target_type=r.target_type or "",
                target_id=r.target_id or "",
                details=r.details or "",
                created_at=_iso(r.created_at),
            )
            for r in rows
        ],
        total=total,
        page=page,
        per_page=per_page,
        total_pages=max(1, ceil(total / per_page)),
    )
