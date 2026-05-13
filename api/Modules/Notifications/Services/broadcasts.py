"""Announcement broadcast Service: who opts in + the subject /
plain-body template.

Like the trial-reminder Service, the actual mail delivery +
template rendering stay in app.py (Flask's `render_template` +
the Resend SDK wrapper). What this module owns:

  - `BROADCAST_PLAIN_BODY` — copy template for the text-part of
    the email.
  - `derive_broadcast_subject(message)` — first non-empty line
    of the announcement, capped at 100 chars; generic fallback
    when the message is empty.
  - `eligible_recipients(db)` — every active user with email +
    `notify_announcement_email=True` + no recorded bounce.

Per CLAUDE.md the broadcast is idempotent on
`Announcement.broadcast_sent_at`. The first successful run
stamps it; subsequent calls (re-run, manual replay, etc.) no-op.
"""
from sqlalchemy.orm import Session


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
