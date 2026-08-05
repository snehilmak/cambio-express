"""Announcement visibility resolution.

Single source of truth for "what banners are showing right now?"
Consumed by `GET /api/v2/announcements/active` (the SPA's
`<AnnouncementBanner>` mounts inside `AppShell`) and by the
superadmin CRUD page's `is_visible` derived flag.

Pure read — no DB writes, no commits.
"""

from sqlalchemy.orm import Session

from api.Modules.Announcements.Models import Announcement, AnnouncementStore
from api.Core.Clock import utc_now


def active_announcements(
    db: Session, store_id: int | None = None,
) -> list[Announcement]:
    """Return announcements visible right now for a given viewer.

    A row is visible when:
      - `is_active` is True, AND
      - `starts_at` is None or already past, AND
      - `expires_at` is None or still in the future, AND
      - it's *global* (no ``AnnouncementStore`` rows) OR *targeted at
        the viewer's store* (``store_id`` matches one of its rows).

    `store_id` is the viewer's store (from the JWT). ``None`` — a
    superadmin, who has no store — sees only global announcements;
    store-targeted banners aren't meant for the platform operator's
    own chrome (they still show up in the superadmin CRUD list).

    Sort order: newest-first by `created_at` so the most recent
    superadmin post lands at the top of the banner stack.
    """
    now = utc_now()
    rows = (
        db.query(Announcement)
          .filter_by(is_active=True)
          .order_by(Announcement.created_at.desc())
          .all()
    )
    windowed = []
    for a in rows:
        if a.starts_at is not None and a.starts_at > now:
            continue
        if a.expires_at is not None and a.expires_at <= now:
            continue
        windowed.append(a)
    if not windowed:
        return []

    ids = [a.id for a in windowed]
    # Announcements that carry ANY targeting row are targeted; the
    # rest are global. Two cheap lookups keep this O(1) queries
    # regardless of how many banners are live.
    targeted_ids = {
        aid for (aid,) in
        db.query(AnnouncementStore.announcement_id)
          .filter(AnnouncementStore.announcement_id.in_(ids))
          .distinct()
    }
    mine_ids: set[int] = set()
    if store_id is not None and targeted_ids:
        mine_ids = {
            aid for (aid,) in
            db.query(AnnouncementStore.announcement_id)
              .filter(
                  AnnouncementStore.announcement_id.in_(ids),
                  AnnouncementStore.store_id == store_id,
              )
        }
    return [
        a for a in windowed
        if a.id not in targeted_ids or a.id in mine_ids
    ]
