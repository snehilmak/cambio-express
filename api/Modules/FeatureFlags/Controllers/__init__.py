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
from api.Modules.Auth.Models import User
from api.Modules.FeatureFlags.Requests import (
    FeatureFlagCreateRequest,
    FeatureFlagListResponse,
    FeatureFlagResponse,
    FeatureFlagRow,
    FeatureFlagToggleRequest,
)


router = APIRouter()


def _require_superadmin_user(db: Session, claims: dict) -> User:
    if claims.get("role") != "superadmin":
        raise HTTPException(
            status_code=403, detail="Superadmin scope required.",
        )
    sub = claims.get("sub")
    if sub is None:
        raise HTTPException(
            status_code=401, detail="JWT is missing the subject claim.",
        )
    user = db.query(User).filter(User.id == int(sub)).one_or_none()
    if user is None:
        raise HTTPException(
            status_code=401, detail="JWT subject does not resolve.",
        )
    return user


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
    _require_superadmin_user(db, claims)
    from app import FeatureFlag
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
    user = _require_superadmin_user(db, claims)
    from app import FeatureFlag
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
    user = _require_superadmin_user(db, claims)
    from app import FeatureFlag
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
    user = _require_superadmin_user(db, claims)
    from app import FeatureFlag, StoreFeatureOverride
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
