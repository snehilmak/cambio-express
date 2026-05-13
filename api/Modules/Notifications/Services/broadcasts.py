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
import os
from datetime import datetime

from sqlalchemy.orm import Session

from api.Modules.Notifications.Services.smtp import send_email
from api.Modules.Notifications.Services.templates import render_email_template


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


def eligible_recipients(db: Session) -> list:
    """Active users who should receive announcement broadcasts.

    Filters:
      - `is_active=True` — disabled accounts skipped.
      - non-empty `email` — can't deliver without an address.
      - `notify_announcement_email=True` — explicit opt-in.
      - `email_bounced_at is None` — drop addresses that already
        hard-bounced so we don't keep hitting Resend's spam
        score.

    Read-only — no DB writes.
    """
    from api.Modules.Tenancy.Models import User
    return (
        db.query(User)
          .filter(
              User.is_active == True,  # noqa: E712 — SQLAlchemy boolean
              User.email != "",
              User.notify_announcement_email == True,  # noqa: E712
              User.email_bounced_at.is_(None),
          )
          .all()
    )


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
    base_url = base_url or os.environ.get(
        "APP_BASE_URL", "https://dinerobook.com",
    )

    ann = session.get(Announcement, announcement_id)
    if ann is None:
        return 0
    if ann.broadcast_sent_at is not None:
        return 0  # already sent — idempotent

    subject = derive_broadcast_subject(ann.message)
    recipients = eligible_recipients(session)
    now = datetime.utcnow()
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
        sent += 1
    ann.broadcast_sent_at = now
    session.commit()
    return sent
