"""Announcement visibility resolution.

Single source of truth for "what banners are showing right now?"
Used by the global banner zone in `base.html` (admin/employee
chrome) and any future surface that wants to render the same
list (e.g. an API endpoint for the mobile app).

Pure read — no DB writes, no commits.
"""
from datetime import datetime

from sqlalchemy.orm import Session

from api.Modules.Announcements.Models import Announcement


def active_announcements(db: Session) -> list[Announcement]:
    """Return announcements visible right now.

    A row is visible when:
      - `is_active` is True, AND
      - `starts_at` is None or already past, AND
      - `expires_at` is None or still in the future.

    Sort order: newest-first by `created_at` so the most recent
    superadmin post lands at the top of the banner stack.
    """
    now = datetime.utcnow()
    rows = (
        db.query(Announcement)
          .filter_by(is_active=True)
          .order_by(Announcement.created_at.desc())
          .all()
    )
    visible = []
    for a in rows:
        if a.starts_at is not None and a.starts_at > now:
            continue
        if a.expires_at is not None and a.expires_at <= now:
            continue
        visible.append(a)
    return visible
