"""FeatureFlags module — Controllers (FastAPI router).

Mounts at `/api/v2/feature-flags/*`. Superadmin-scoped CRUD over
the platform-wide flag registry the legacy
`/superadmin/controls?tab=feature-flags` page already manages.

  GET    /feature-flags             → list every flag
  POST   /feature-flags             → create
  POST   /feature-flags/{key}/toggle → flip enabled_by_default
  DELETE /feature-flags/{key}       → hard-delete

Per-store overrides (StoreFeatureOverride) ship in a follow-up
PR — they need a different audit trail since they're per-tenant
not platform-wide.

Every mutation goes through `_audit()` so the
`/superadmin/audit-log` feed stays the single source of truth
(CLAUDE.md invariant #7).
"""
from fastapi import APIRouter, Depends, HTTPException, Path
from sqlalchemy.orm import Session

from api.Core.Database import get_db
from api.Modules.Audit.Services import record_superadmin_action
from api.Modules.Auth.Controllers import get_principal
from api.Modules.Auth.Services import resolve_superadmin_user
from api.Modules.FeatureFlags.Requests import (
    FeatureFlagCreateRequest,
    FeatureFlagListResponse,
    FeatureFlagResponse,
    FeatureFlagRow,
    FeatureFlagToggleRequest,
    StoreOverrideListResponse,
    StoreOverrideRequest,
    StoreOverrideResponse,
    StoreOverrideRow,
)


router = APIRouter()


def _audit(db, user, action, *, target_id="", details=""):
    record_superadmin_action(
        db,
        admin_id=user.id,
        admin_name=user.full_name or user.username or "",
        action=action,
        target_type="feature_flag",
        target_id=target_id,
        details=details,
    )


def _adapt(f) -> FeatureFlagRow:
    return FeatureFlagRow(
        id=f.id,
        key=f.key,
        label=f.label or "",
        description=f.description or "",
        enabled_by_default=bool(f.enabled_by_default),
        created_at=f.created_at.isoformat() if f.created_at else "",
    )


@router.get("", response_model=FeatureFlagListResponse)
def list_route(
    db: Session = Depends(get_db),
    claims: dict = Depends(get_principal),
) -> FeatureFlagListResponse:
    resolve_superadmin_user(db, claims)
    from api.Modules.Billing.Models import FeatureFlag
    rows = (
        db.query(FeatureFlag).order_by(FeatureFlag.key.asc()).all()
    )
    return FeatureFlagListResponse(
        rows=[_adapt(f) for f in rows], total=len(rows),
    )


@router.post("", response_model=FeatureFlagResponse, status_code=201)
def create_route(
    body: FeatureFlagCreateRequest,
    db: Session = Depends(get_db),
    claims: dict = Depends(get_principal),
) -> FeatureFlagResponse:
    user = resolve_superadmin_user(db, claims)
    from api.Modules.Billing.Models import FeatureFlag
    if db.query(FeatureFlag).filter(FeatureFlag.key == body.key).one_or_none():
        raise HTTPException(
            status_code=409,
            detail={
                "field": "key",
                "message": f"Flag '{body.key}' already exists.",
            },
        )
    f = FeatureFlag(
        key=body.key,
        label=body.label.strip(),
        description=body.description.strip(),
        enabled_by_default=body.enabled_by_default,
    )
    db.add(f); db.flush()
    _audit(
        db, user, "create_feature_flag",
        target_id=body.key,
        details=f"enabled_by_default={body.enabled_by_default}",
    )
    db.commit()
    return FeatureFlagResponse(flag=_adapt(f))


@router.post("/{key}/toggle", response_model=FeatureFlagResponse)
def toggle_route(
    body: FeatureFlagToggleRequest,
    key: str = Path(..., min_length=1, max_length=60),
    db: Session = Depends(get_db),
    claims: dict = Depends(get_principal),
) -> FeatureFlagResponse:
    user = resolve_superadmin_user(db, claims)
    from api.Modules.Billing.Models import FeatureFlag
    f = db.query(FeatureFlag).filter(FeatureFlag.key == key).one_or_none()
    if f is None:
        raise HTTPException(status_code=404, detail="Feature flag not found")
    f.enabled_by_default = body.enabled_by_default
    _audit(
        db, user, "toggle_feature_flag",
        target_id=key,
        details=f"enabled_by_default={body.enabled_by_default}",
    )
    db.commit()
    return FeatureFlagResponse(flag=_adapt(f))


@router.delete("/{key}", status_code=204)
def delete_route(
    key: str = Path(..., min_length=1, max_length=60),
    db: Session = Depends(get_db),
    claims: dict = Depends(get_principal),
) -> None:
    user = resolve_superadmin_user(db, claims)
    from api.Modules.Billing.Models import FeatureFlag, StoreFeatureOverride
    f = db.query(FeatureFlag).filter(FeatureFlag.key == key).one_or_none()
    if f is None:
        raise HTTPException(status_code=404, detail="Feature flag not found")
    # Cascade per-store overrides too — they reference the key
    # directly and would orphan otherwise.
    db.query(StoreFeatureOverride).filter(
        StoreFeatureOverride.flag_key == key,
    ).delete()
    db.delete(f)
    _audit(
        db, user, "delete_feature_flag",
        target_id=key,
        details=(f.label or "")[:80],
    )
    db.commit()
    return None


# ── Per-store overrides ─────────────────────────────────────


def _adapt_override(o, *, store) -> StoreOverrideRow:
    return StoreOverrideRow(
        store_id=o.store_id,
        store_slug=store.slug or "" if store else "",
        store_name=store.name or "" if store else "",
        flag_key=o.flag_key,
        enabled=bool(o.enabled),
        updated_at=o.updated_at.isoformat() if o.updated_at else "",
    )


@router.get("/{key}/overrides", response_model=StoreOverrideListResponse)
def list_overrides_route(
    key: str = Path(..., min_length=1, max_length=60),
    db: Session = Depends(get_db),
    claims: dict = Depends(get_principal),
) -> StoreOverrideListResponse:
    """Every store-level override for a given flag, ordered by
    store name. Useful for the superadmin to see which customers
    have a non-default value at a glance."""
    resolve_superadmin_user(db, claims)
    from api.Modules.Billing.Models import StoreFeatureOverride
    from api.Modules.Tenancy.Models import Store
    rows = (
        db.query(StoreFeatureOverride)
          .filter(StoreFeatureOverride.flag_key == key)
          .all()
    )
    if not rows:
        return StoreOverrideListResponse(rows=[], total=0)
    sids = [r.store_id for r in rows]
    stores = {
        s.id: s for s in db.query(Store).filter(Store.id.in_(sids)).all()
    }
    out = sorted(
        [_adapt_override(r, store=stores.get(r.store_id)) for r in rows],
        key=lambda x: x.store_name.lower(),
    )
    return StoreOverrideListResponse(rows=out, total=len(out))


@router.put(
    "/{key}/stores/{store_id}", response_model=StoreOverrideResponse,
)
def upsert_override_route(
    body: StoreOverrideRequest,
    key: str = Path(..., min_length=1, max_length=60),
    store_id: int = Path(..., ge=1),
    db: Session = Depends(get_db),
    claims: dict = Depends(get_principal),
) -> StoreOverrideResponse:
    """Set (or update) a per-store override. The flag must exist
    globally; the target store must exist. Idempotent."""
    user = resolve_superadmin_user(db, claims)
    from datetime import datetime
    from api.Modules.Billing.Models import FeatureFlag, StoreFeatureOverride
    from api.Modules.Tenancy.Models import Store
    flag = db.query(FeatureFlag).filter(FeatureFlag.key == key).one_or_none()
    if flag is None:
        raise HTTPException(status_code=404, detail="Feature flag not found")
    store = db.get(Store, store_id)
    if store is None:
        raise HTTPException(status_code=404, detail="Store not found")
    o = (
        db.query(StoreFeatureOverride)
          .filter(
              StoreFeatureOverride.flag_key == key,
              StoreFeatureOverride.store_id == store_id,
          )
          .one_or_none()
    )
    if o is None:
        o = StoreFeatureOverride(
            store_id=store_id, flag_key=key,
            enabled=body.enabled, updated_by=user.id,
        )
        db.add(o); db.flush()
    else:
        o.enabled = body.enabled
        o.updated_at = datetime.utcnow()
        o.updated_by = user.id
    _audit(
        db, user, "set_feature_override",
        target_id=f"{key}:{store_id}",
        details=f"enabled={body.enabled}",
    )
    db.commit()
    return StoreOverrideResponse(override=_adapt_override(o, store=store))


@router.delete("/{key}/stores/{store_id}", status_code=204)
def clear_override_route(
    key: str = Path(..., min_length=1, max_length=60),
    store_id: int = Path(..., ge=1),
    db: Session = Depends(get_db),
    claims: dict = Depends(get_principal),
) -> None:
    """Clear a per-store override — the store reverts to the
    flag's global default. 404 only when no override exists, so
    DELETE is idempotent for existing overrides."""
    user = resolve_superadmin_user(db, claims)
    from api.Modules.Billing.Models import StoreFeatureOverride
    o = (
        db.query(StoreFeatureOverride)
          .filter(
              StoreFeatureOverride.flag_key == key,
              StoreFeatureOverride.store_id == store_id,
          )
          .one_or_none()
    )
    if o is None:
        raise HTTPException(status_code=404, detail="Override not found")
    db.delete(o)
    _audit(
        db, user, "clear_feature_override",
        target_id=f"{key}:{store_id}",
    )
    db.commit()
    return None
