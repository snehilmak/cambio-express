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

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from sqlalchemy.orm import Session

from api.Core.Database import get_db
from api.Modules.Audit.Services import record_superadmin_action
from api.Modules.Auth.Controllers import get_principal
from api.Modules.Auth.Models import User
from api.Modules.Superadmin.Requests import (
    DiscountCodeListResponse,
    DiscountCodeResponse,
    DiscountCodeRow,
    DiscountCodeToggleRequest,
    SuperadminAnomalyListResponse,
    SuperadminAnomalyRow,
    SuperadminAuditListResponse,
    SuperadminAuditRow,
    SuperadminStoreCreateRequest,
    SuperadminStoreDetailResponse,
    SuperadminStoreDetailRow,
    SuperadminStoreListResponse,
    SuperadminStoreRow,
    SuperadminStoreUpdateRequest,
)


router = APIRouter()


def _require_superadmin(claims: dict) -> None:
    if claims.get("role") != "superadmin":
        raise HTTPException(
            status_code=403,
            detail="Superadmin scope required.",
        )


def _require_superadmin_user(db: Session, claims: dict) -> User:
    """Resolve JWT → User and gate on role=superadmin. Returns the
    User row so the audit trail can stamp admin_id + admin_name from
    canonical DB values (not whatever the JWT claims happen to carry).
    Used by the mutation endpoints; the read-only endpoints continue
    to call the cheaper `_require_superadmin(claims)` since they
    don't audit."""
    _require_superadmin(claims)
    sub = claims.get("sub")
    if sub is None:
        raise HTTPException(
            status_code=401, detail="JWT is missing the subject claim.",
        )
    user = db.query(User).filter(User.id == int(sub)).one_or_none()
    if user is None:
        raise HTTPException(
            status_code=401, detail="JWT subject does not resolve to a user.",
        )
    return user


def _audit_store(db: Session, user: User, action: str,
                 *, target_id: str = "", details: str = "") -> None:
    """Thin wrapper that goes straight to the Service so we don't need
    Flask's request context (the legacy `record_audit` reads
    `current_user()` from Flask session, which isn't set inside a
    FastAPI route through the dispatcher). Per CLAUDE.md invariant
    #7: every superadmin mutation MUST call record_audit."""
    record_superadmin_action(
        db,
        admin_id=user.id,
        admin_name=user.full_name or user.username or "",
        action=action,
        target_type="store",
        target_id=target_id,
        details=details,
    )


def _iso(dt) -> str:
    return dt.isoformat() if dt else ""


def _normalize_slug(raw: str) -> str:
    """Mirrors the legacy `superadmin_new_store` slug normalization:
    strip + lowercase + spaces-to-dashes. Centralized here so the
    create + patch paths agree on what 'the same slug' means."""
    return (raw or "").strip().lower().replace(" ", "-")


def _adapt_detail(s) -> SuperadminStoreDetailRow:
    return SuperadminStoreDetailRow(
        store_id=s.id,
        name=s.name or "",
        slug=s.slug or "",
        email=s.email or "",
        phone=s.phone or "",
        address=s.address or "",
        plan=s.plan or "trial",
        billing_cycle=s.billing_cycle or "",
        is_active=bool(s.is_active),
        federal_tax_rate=float(s.federal_tax_rate or 0.0),
        created_at=_iso(s.created_at),
        trial_ends_at=_iso(s.trial_ends_at),
        grace_ends_at=_iso(s.grace_ends_at),
        data_retention_until=_iso(s.data_retention_until),
        stripe_customer_id=s.stripe_customer_id or "",
        stripe_subscription_id=s.stripe_subscription_id or "",
    )


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


@router.get("/stores/{store_id}", response_model=SuperadminStoreDetailResponse)
def get_store_route(
    store_id: int = Path(..., ge=1),
    db: Session = Depends(get_db),
    claims: dict = Depends(get_principal),
) -> SuperadminStoreDetailResponse:
    """Single-store payload for the SPA edit form.

    Read-only — feeds `/app/superadmin/stores/:id/edit`. Returns
    every field the edit form binds against (identity + plan +
    federal_tax_rate). 404 when the row doesn't exist."""
    _require_superadmin(claims)
    from app import Store
    s = db.query(Store).filter(Store.id == store_id).one_or_none()
    if s is None:
        raise HTTPException(status_code=404, detail="Store not found")
    return SuperadminStoreDetailResponse(store=_adapt_detail(s))


@router.post(
    "/stores",
    response_model=SuperadminStoreDetailResponse,
    status_code=201,
)
def create_store_route(
    body: SuperadminStoreCreateRequest,
    db: Session = Depends(get_db),
    claims: dict = Depends(get_principal),
) -> SuperadminStoreDetailResponse:
    """Mint a new store + its initial admin user in one transaction.

    Mirrors the legacy `superadmin_new_store` POST handler: builds a
    `Store` row, attaches the operator-supplied admin User, and
    records a `create_store` audit entry. The transaction is atomic
    — if the admin User insert fails the Store row rolls back.

    Slug normalization (lowercase + dashes) matches the legacy
    handler. Duplicate slugs return 409 with `field=slug` so the SPA
    can render the field-level error inline."""
    user = _require_superadmin_user(db, claims)
    from app import Store
    slug = _normalize_slug(body.slug)
    if not slug:
        raise HTTPException(
            status_code=422,
            detail={"field": "slug", "message": "Slug cannot be empty."},
        )
    if db.query(Store).filter(Store.slug == slug).one_or_none():
        raise HTTPException(
            status_code=409,
            detail={
                "field": "slug",
                "message": f"Slug '{slug}' is already taken.",
            },
        )
    s = Store(
        name=body.name.strip(),
        slug=slug,
        email=body.email.strip(),
        phone=body.phone.strip(),
        address=body.address.strip(),
        plan=body.plan,
    )
    db.add(s)
    db.flush()
    a = User(
        store_id=s.id,
        username=body.admin_username.strip(),
        full_name=body.admin_name.strip(),
        role="admin",
    )
    a.set_password(body.admin_password)
    db.add(a)
    _audit_store(
        db, user, "create_store",
        target_id=str(s.id),
        details=s.slug,
    )
    db.commit()
    return SuperadminStoreDetailResponse(store=_adapt_detail(s))


@router.patch(
    "/stores/{store_id}",
    response_model=SuperadminStoreDetailResponse,
)
def update_store_route(
    body: SuperadminStoreUpdateRequest,
    store_id: int = Path(..., ge=1),
    db: Session = Depends(get_db),
    claims: dict = Depends(get_principal),
) -> SuperadminStoreDetailResponse:
    """Update an existing store's identity / plan fields.

    Every field is optional — only the keys present in the body get
    applied. Slug uniqueness is re-validated on rename (a duplicate
    returns 409 with `field=slug`). The audit row's `details` lists
    the keys that changed so the audit log shows what was touched
    even when the values are sensitive (email).

    Out of scope (use the dedicated endpoints):
      - Trial extension → POST /superadmin/stores/{id}/extend-trial
      - Toggle active   → POST /superadmin/stores/{id}/toggle-active
      - Comp plan       → POST /superadmin/stores/{id}/comp-plan
      - Add-on toggle   → POST /superadmin/stores/{id}/addons/...
    Those flows ship separately because they have their own audit
    actions + side effects (cancel-related state cleanup, retention
    timer reset, etc.)."""
    user = _require_superadmin_user(db, claims)
    from app import Store
    s = db.query(Store).filter(Store.id == store_id).one_or_none()
    if s is None:
        raise HTTPException(status_code=404, detail="Store not found")

    changed: list[str] = []
    if body.slug is not None:
        new_slug = _normalize_slug(body.slug)
        if not new_slug:
            raise HTTPException(
                status_code=422,
                detail={"field": "slug", "message": "Slug cannot be empty."},
            )
        if new_slug != s.slug:
            dup = (
                db.query(Store)
                  .filter(Store.slug == new_slug, Store.id != s.id)
                  .one_or_none()
            )
            if dup is not None:
                raise HTTPException(
                    status_code=409,
                    detail={
                        "field": "slug",
                        "message": f"Slug '{new_slug}' is already taken.",
                    },
                )
            s.slug = new_slug
            changed.append("slug")
    if body.name is not None and body.name.strip() != (s.name or ""):
        s.name = body.name.strip()
        changed.append("name")
    if body.email is not None and body.email.strip() != (s.email or ""):
        s.email = body.email.strip()
        changed.append("email")
    if body.phone is not None and body.phone.strip() != (s.phone or ""):
        s.phone = body.phone.strip()
        changed.append("phone")
    if body.address is not None and body.address.strip() != (s.address or ""):
        s.address = body.address.strip()
        changed.append("address")
    if body.plan is not None and body.plan != (s.plan or ""):
        s.plan = body.plan
        changed.append("plan")
    if (
        body.federal_tax_rate is not None
        and float(body.federal_tax_rate) != float(s.federal_tax_rate or 0.0)
    ):
        s.federal_tax_rate = float(body.federal_tax_rate)
        changed.append("federal_tax_rate")

    if changed:
        _audit_store(
            db, user, "update_store",
            target_id=str(s.id),
            details=",".join(changed),
        )
    db.commit()
    return SuperadminStoreDetailResponse(store=_adapt_detail(s))


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


@router.get("/anomalies", response_model=SuperadminAnomalyListResponse)
def list_anomalies_route(
    db: Session = Depends(get_db),
    claims: dict = Depends(get_principal),
) -> SuperadminAnomalyListResponse:
    """Read-only feed of platform-wide anomalies (quiet stores,
    big over/short variances) computed against today's date.

    Backed by `compute_platform_anomalies()` — same Service the
    legacy /superadmin/controls overview already runs on every
    page load. Cheap to recompute on each call.
    """
    _require_superadmin(claims)
    from api.Modules.Superadmin.Services import compute_platform_anomalies
    raw = compute_platform_anomalies(db)
    rows = [
        SuperadminAnomalyRow(
            kind=a["kind"],
            severity=a["severity"],
            store_id=a["store"].id,
            store_name=a["store"].name or "",
            store_slug=a["store"].slug or "",
            description=a["description"],
            href=a.get("href", ""),
        )
        for a in raw
    ]
    return SuperadminAnomalyListResponse(rows=rows, total=len(rows))


# ── Discount codes (list + toggle) ──────────────────────────


def _adapt_discount(d) -> DiscountCodeRow:
    from datetime import datetime as _dt
    expired = (
        d.expires_at is not None and d.expires_at < _dt.utcnow()
    )
    capped = (
        d.max_redemptions is not None
        and (d.redeemed_count or 0) >= d.max_redemptions
    )
    return DiscountCodeRow(
        id=d.id,
        code=d.code,
        label=d.label or "",
        percent_off=d.percent_off,
        amount_off_cents=d.amount_off_cents,
        value_label=d.value_label,
        duration=d.duration or "once",
        duration_in_months=d.duration_in_months,
        max_redemptions=d.max_redemptions,
        redeemed_count=d.redeemed_count or 0,
        expires_at=_iso(d.expires_at),
        is_active=bool(d.is_active),
        is_redeemable=bool(d.is_active) and not expired and not capped,
        stripe_coupon_id=d.stripe_coupon_id or "",
        stripe_promotion_code_id=d.stripe_promotion_code_id or "",
        created_at=_iso(d.created_at),
    )


@router.get("/discounts", response_model=DiscountCodeListResponse)
def list_discounts_route(
    db: Session = Depends(get_db),
    claims: dict = Depends(get_principal),
) -> DiscountCodeListResponse:
    """List every minted promo code (newest first). Read-only by
    design — Stripe coupon mint + new-code generation stays on the
    legacy site for now (those need careful Stripe error handling).
    This endpoint only renders + toggles; it never makes Stripe
    API calls."""
    _require_superadmin(claims)
    from app import DiscountCode
    rows = (
        db.query(DiscountCode)
          .order_by(DiscountCode.created_at.desc())
          .all()
    )
    return DiscountCodeListResponse(
        rows=[_adapt_discount(d) for d in rows], total=len(rows),
    )


@router.post(
    "/discounts/{discount_id}/toggle",
    response_model=DiscountCodeResponse,
)
def toggle_discount_route(
    body: DiscountCodeToggleRequest,
    discount_id: int,
    db: Session = Depends(get_db),
    claims: dict = Depends(get_principal),
) -> DiscountCodeResponse:
    """Flip a discount's `is_active` flag without touching Stripe.
    Inactive codes still exist in the DB + Stripe (so historical
    invoices keep their references) but new Checkout sessions
    that try to apply them are rejected by `is_redeemable`."""
    _require_superadmin(claims)
    from app import DiscountCode
    d = db.query(DiscountCode).filter(
        DiscountCode.id == discount_id,
    ).one_or_none()
    if d is None:
        raise HTTPException(status_code=404, detail="Discount code not found")
    d.is_active = body.is_active
    db.commit()
    return DiscountCodeResponse(discount=_adapt_discount(d))
