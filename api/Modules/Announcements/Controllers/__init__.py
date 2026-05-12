"""Announcements module — Controllers (FastAPI router).

Mounts at `/api/v2/announcements/*`. Endpoints:

  GET    /announcements          → list every announcement (newest first)
  POST   /announcements          → create a new banner (+ optional broadcast)
  POST   /announcements/{id}/toggle → enable / disable
  DELETE /announcements/{id}     → hard-delete

Auth: requires JWT principal with role="superadmin". Mirrors the
legacy /superadmin/announcements/* form handlers but returns JSON
envelopes the SPA can render directly.

Every mutation calls `record_audit()` so the
`/superadmin/audit-log` view stays the single source of truth for
"who did what" — same invariant as the legacy site (CLAUDE.md
invariant #7).
"""
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Path
from sqlalchemy.orm import Session

from api.Core.Database import get_db
from api.Modules.Announcements.Requests import (
    AnnouncementCreateRequest,
    AnnouncementListResponse,
    AnnouncementResponse,
    AnnouncementRow,
    AnnouncementToggleRequest,
)
from api.Modules.Audit.Services import record_superadmin_action
from api.Modules.Auth.Controllers import get_principal
from api.Modules.Auth.Models import User


router = APIRouter()


def _require_superadmin_user(db: Session, claims: dict) -> User:
    """Resolve JWT → User and gate on role=superadmin. Returns the
    User row so the audit trail can stamp admin_id + admin_name from
    canonical DB values (not whatever the JWT claims happen to carry)."""
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
            status_code=401, detail="JWT subject does not resolve to a user.",
        )
    return user


def _audit(db: Session, user: User, action: str, *,
           target_type: str = "", target_id: str = "", details: str = ""):
    """Thin wrapper that goes straight to the Service so we don't need
    Flask's request context (the legacy `record_audit` reads
    `current_user()` from Flask session, which isn't set inside a
    FastAPI route through the dispatcher)."""
    record_superadmin_action(
        db,
        admin_id=user.id,
        admin_name=user.full_name or user.username or "",
        action=action,
        target_type=target_type,
        target_id=target_id,
        details=details,
    )


def _iso(dt) -> str:
    return dt.isoformat() if dt else ""


def _is_visible(a) -> bool:
    """Mirrors the active_announcements predicate: row must be
    is_active AND inside its starts_at/expires_at window."""
    if not a.is_active:
        return False
    now = datetime.utcnow()
    if a.starts_at and now < a.starts_at:
        return False
    if a.expires_at and now > a.expires_at:
        return False
    return True


def _adapt(a) -> AnnouncementRow:
    return AnnouncementRow(
        id=a.id,
        message=a.message or "",
        level=a.level or "info",
        is_active=bool(a.is_active),
        is_visible=_is_visible(a),
        starts_at=_iso(a.starts_at),
        expires_at=_iso(a.expires_at),
        created_at=_iso(a.created_at),
        created_by=a.created_by,
        broadcast_requested=bool(a.broadcast_requested),
        broadcast_sent_at=_iso(getattr(a, "broadcast_sent_at", None)),
    )


@router.get("", response_model=AnnouncementListResponse)
def list_route(
    db: Session = Depends(get_db),
    claims: dict = Depends(get_principal),
) -> AnnouncementListResponse:
    """Every announcement, newest first. Includes inactive + expired
    rows so the superadmin has the full history; the SPA can dim
    the rows where `is_visible` is False."""
    _require_superadmin_user(db, claims)
    from app import Announcement
    rows = (
        db.query(Announcement)
          .order_by(Announcement.created_at.desc())
          .all()
    )
    return AnnouncementListResponse(
        rows=[_adapt(a) for a in rows], total=len(rows),
    )


@router.post("", response_model=AnnouncementResponse, status_code=201)
def create_route(
    body: AnnouncementCreateRequest,
    db: Session = Depends(get_db),
    claims: dict = Depends(get_principal),
) -> AnnouncementResponse:
    """Mint a new banner. `expires_days=0` (or omitted) means no
    expiry. `broadcast=True` queues the message for the broadcast-
    email fan-out (one-shot at create time).

    `start_at_iso` schedules the banner for a future timestamp —
    the visibility helper (`active_announcements`) skips rows whose
    `starts_at` is still in the future, so a scheduled announcement
    silently waits until its time arrives. Empty / unparseable
    falls back to "start now"."""
    user = _require_superadmin_user(db, claims)
    from app import Announcement
    now = datetime.utcnow()
    starts_at = _parse_starts_at(body.start_at_iso, fallback=now)
    # expires_days is measured from the start time so a scheduled
    # banner gets its full visibility window — "10-day banner that
    # goes live next Monday" expires 10 days after Monday, not 10
    # days from create time.
    expires_at = (
        starts_at + timedelta(days=body.expires_days)
        if body.expires_days else None
    )
    a = Announcement(
        message=body.message[:2000],
        level=body.level,
        is_active=True,
        starts_at=starts_at,
        expires_at=expires_at,
        created_by=user.id,
        broadcast_requested=body.broadcast,
    )
    db.add(a); db.flush()
    scheduled = starts_at > now
    _audit(
        db, user, "create_announcement",
        target_type="announcement", target_id=str(a.id),
        details=(
            f"level={body.level}, broadcast={body.broadcast}, "
            f"scheduled={scheduled}"
        ),
    )
    db.commit()
    return AnnouncementResponse(announcement=_adapt(a))


def _parse_starts_at(raw: str, *, fallback: datetime) -> datetime:
    """Parse the ISO-8601 datetime sent by the SPA. Accepts both
    naive ("2026-05-15T14:00") and offset-aware ("...Z" / "+00:00")
    forms; offset-aware values are converted to naive UTC so the
    column stays homogeneous with the rest of the model.

    Bad / empty input falls back to the caller-supplied `fallback`
    so a typo never blocks the create — the superadmin can still
    fix the schedule via a follow-up edit (or delete + recreate)."""
    if not raw or not raw.strip():
        return fallback
    text = raw.strip()
    # datetime.fromisoformat in 3.11+ handles "Z" suffix; coerce to
    # the "+00:00" form for older runtimes just in case.
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return fallback
    if parsed.tzinfo is not None:
        # Convert to UTC + drop tzinfo (Announcement.starts_at is naive UTC).
        from datetime import timezone
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


@router.post(
    "/{ann_id}/toggle", response_model=AnnouncementResponse,
)
def toggle_route(
    body: AnnouncementToggleRequest,
    ann_id: int = Path(..., ge=1),
    db: Session = Depends(get_db),
    claims: dict = Depends(get_principal),
) -> AnnouncementResponse:
    user = _require_superadmin_user(db, claims)
    from app import Announcement
    a = db.query(Announcement).filter(Announcement.id == ann_id).one_or_none()
    if a is None:
        raise HTTPException(status_code=404, detail="Announcement not found")
    a.is_active = body.is_active
    _audit(
        db, user, "toggle_announcement",
        target_type="announcement", target_id=str(a.id),
        details=f"is_active={body.is_active}",
    )
    db.commit()
    return AnnouncementResponse(announcement=_adapt(a))


@router.delete("/{ann_id}", status_code=204)
def delete_route(
    ann_id: int = Path(..., ge=1),
    db: Session = Depends(get_db),
    claims: dict = Depends(get_principal),
) -> None:
    user = _require_superadmin_user(db, claims)
    from app import Announcement
    a = db.query(Announcement).filter(Announcement.id == ann_id).one_or_none()
    if a is None:
        raise HTTPException(status_code=404, detail="Announcement not found")
    _audit(
        db, user, "delete_announcement",
        target_type="announcement", target_id=str(a.id),
        details=(a.message or "")[:80],
    )
    db.delete(a)
    db.commit()
    return None
