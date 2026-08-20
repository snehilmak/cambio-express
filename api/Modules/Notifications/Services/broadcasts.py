"""Announcement broadcast Service: eligibility + fanout
orchestrator.

Two halves:

  - **Pure queries**: ``derive_broadcast_subject`` and
    ``eligible_recipients`` — easy to unit-test, no side effects.
  - **Side-effect orchestrator**: ``run(session, announcement_id,
    base_url=None)`` is the CLI entry point — renders the email
    + delivers via SMTP + stamps ``Announcement.broadcast_sent_at``.

Per CLAUDE.md the broadcast is idempotent on
``Announcement.broadcast_sent_at``. ``run()`` checks the flag and
no-ops on second call; subsequent calls (re-run, manual replay,
etc.) return 0.
"""
from typing import Any

from sqlalchemy.orm import Session

from api.Modules.Notifications.Services.smtp import send_email
from api.Modules.Notifications.Services.templates import render_email_template
from api.Core.Clock import utc_now


# Subject fallback when the announcement message is empty / blank.
_GENERIC_BROADCAST_SUBJECT = "A message from DineroBook"
_BROADCAST_SUBJECT_MAX = 100


BROADCAST_PLAIN_BODY = """\
Announcement from DineroBook

{message}

— DineroBook ({base_url})

Don't want announcement emails? Turn them off:
  {notifications_url}
"""


def derive_broadcast_subject(message: str | None) -> str:
    """Pull a subject line from `message`.

    Uses the first non-empty line, trimmed and capped at 100
    chars. Falls back to a generic subject when the message is
    empty / whitespace-only — keeps the emailbox-preview clean.
    """
    text = (message or "").strip()
    if not text:
        return _GENERIC_BROADCAST_SUBJECT
    first_line = text.split("\n", 1)[0]
    return first_line[:_BROADCAST_SUBJECT_MAX] or _GENERIC_BROADCAST_SUBJECT


def eligible_recipients(
    db: Session, *, store_ids: list[int] | None = None,
) -> list[Any]:
    """Active users who should receive announcement broadcasts.

    Filters:
      - `is_active=True` — disabled accounts skipped.
      - non-empty `email` — can't deliver without an address.
      - `notify_announcement_email=True` — explicit opt-in.
      - `email_bounced_at is None` — drop addresses that already
        hard-bounced so we don't keep hitting Resend's spam
        score.

    `store_ids` restricts delivery to users in those stores — used
    when the announcement is *targeted*. ``None`` (the default) means
    the announcement is global and every opted-in user is eligible.
    An empty list would match no users; callers pass ``None`` for
    "everyone", never ``[]``.

    Read-only — no DB writes.
    """
    from api.Modules.Tenancy.Models import User
    q = (
        db.query(User)
          .filter(
              User.is_active == True,  # noqa: E712 — SQLAlchemy boolean
              User.email != "",
              User.notify_announcement_email == True,  # noqa: E712
              User.email_bounced_at.is_(None),
          )
    )
    if store_ids is not None:
        q = q.filter(User.store_id.in_(store_ids))
    return q.all()


def run(
    session: Session,
    announcement_id: int,
    *,
    base_url: str | None = None,
) -> int:
    """Fan out an announcement email to every opted-in user.

    Returns the count of emails actually attempted (not counting
    users filtered out). Idempotent: the first successful run
    stamps ``Announcement.broadcast_sent_at`` and subsequent
    calls no-op.

    The caller owns the session lifecycle — this function commits
    inside the session on a successful broadcast (so the dedup
    stamp lands), but never closes the session.
    """
    from api.Modules.Announcements.Models import Announcement
    from api.Core.Urls import get_base_url
    base_url = base_url or get_base_url()

    ann = session.get(Announcement, announcement_id)
    if ann is None:
        return 0
    if ann.broadcast_sent_at is not None:
        return 0  # already sent — idempotent

    subject = derive_broadcast_subject(ann.message)
    # Targeted announcements only email users in the target stores;
    # a global announcement (no targeting rows) reaches everyone.
    from api.Modules.Announcements.Models import AnnouncementStore
    target_ids = [
        sid for (sid,) in
        session.query(AnnouncementStore.store_id)
               .filter(AnnouncementStore.announcement_id == ann.id)
               .all()
    ]
    recipients = eligible_recipients(
        session, store_ids=target_ids or None,
    )
    now = utc_now()
    notifications_url = f"{base_url}/account/notifications"
    plain_body = BROADCAST_PLAIN_BODY.format(
        message=ann.message,
        base_url=base_url,
        notifications_url=notifications_url,
    )

    sent = 0
    for u in recipients:
        html = render_email_template(
            "emails/announcement.html",
            preheader=ann.message[:120],
            subject=subject,
            message=ann.message,
            level=ann.level or "info",
            app_url=base_url,
            notifications_url=notifications_url,
            year=now.year,
            base_url=base_url,
        )
        send_email(session, u.email, subject, plain_body, html)
        # Fan out a Web Push notification too — best-effort, doesn't
        # block the email send if VAPID isn't configured (the helper
        # short-circuits returning 0) or pywebpush isn't installed.
        # ``push.send_push`` cleans up dead subscriptions itself so
        # we don't accumulate stale rows.  Honors the per-kind push
        # toggle so a user who opted out of announcement pushes
        # still gets the email (default-allow keeps existing users
        # on the same flow).
        try:
            from api.Modules.Notifications.Services.push import (
                send_push, user_wants_push,
            )
            if user_wants_push(u, "announcement"):
                send_push(
                    session,
                    user_id=int(u.id),
                    title=subject,
                    body=ann.message[:200],
                    url="/app/dashboard",
                    tag=f"announcement:{ann.id}",
                )
        except Exception as exc:  # pragma: no cover — push is best-effort
            # Never let a push failure 5xx the broadcast job.
            import logging
            logging.getLogger(__name__).warning(
                "announcement push failed for user %s: %s", u.id, exc,
            )
        sent += 1
    setattr(ann, "broadcast_sent_at", now)
    session.commit()
    return sent


def broadcast_announcement(announcement_id: int) -> int:
    """Worker entry-point for the announcement broadcast fan-out.

    Takes a primitive ``announcement_id`` (not the SQLAlchemy ORM
    object) so the function can be queued by RQ — see
    ``api.Core.Jobs.enqueue``. Opens its own ``SessionLocal``
    since the caller's session is already closed by the time the
    worker runs.

    Returns the count of emails sent, mirroring ``run()``.
    Idempotent — the underlying ``run()`` already no-ops when
    ``broadcast_sent_at`` is set.
    """
    from api.Core.Database import SessionLocal

    with SessionLocal() as session:
        return run(session, announcement_id)
