"""Transactional email send + SMTP health probe.

Two pieces:

  - `send_email(db, to_addr, subject, body, html=None)` —
    transactional send via stdlib `smtplib`. Multipart/alternative
    when `html` is provided so plaintext clients still get a
    readable fallback. Returns True on success, False on failure
    or when SMTP isn't configured.

    Bounce suppression: if a `User` row with this email got
    stamped by a hard-bounce webhook, the send is skipped — keeps
    us from hammering the provider with guaranteed-failing
    addresses (Resend penalises that as a sender-reputation hit).

  - `health_check(db)` — dict describing email-delivery state,
    matching the shape of the Stripe health-check so the template
    stays symmetric. Doesn't do a live SMTP probe — reads the
    module-level `last_attempt` (updated on every send) plus
    delivery-event totals from `EmailEvent`.

The module-level `last_attempt` dict is the one piece of mutable
global state — it's the bridge from "last send" to "Overview
health card" without round-tripping the SMTP server. Tests reset
it via the `reset_last_attempt()` helper.
"""
import logging
import os
import smtplib
from datetime import datetime, timedelta
from email.message import EmailMessage

from sqlalchemy import func
from sqlalchemy.orm import Session


logger = logging.getLogger(__name__)


# Mutable module-level state — the Overview health card reads
# this instead of round-tripping the SMTP server. Reset between
# test runs via `reset_last_attempt()`.
last_attempt: dict = {
    "status": "unknown", "error": "", "when": None,
    "last_to_domain": "", "last_subject": "",
}


def reset_last_attempt() -> None:
    """Reset the module-level `last_attempt` to its initial
    'unknown' state. Used in test setup so prior test sends
    don't leak."""
    last_attempt.clear()
    last_attempt.update({
        "status": "unknown", "error": "", "when": None,
        "last_to_domain": "", "last_subject": "",
    })


def send_email(
    db: Session,
    to_addr: str,
    subject: str,
    body: str,
    html: str | None = None,
) -> bool:
    """Send a transactional email. Returns True on success, False
    on failure or when SMTP isn't configured. Every attempt
    updates `last_attempt` so the superadmin health card reflects
    the most recent outcome.

    Multipart/alternative when `html` is given — keeps the
    plaintext fallback for accessibility + spam-filter signal.

    Env vars required: `SMTP_HOST`, `SMTP_USER`, `SMTP_PASS`.
    Optional: `SMTP_PORT` (default 587), `SMTP_FROM`
    (default `SMTP_USER`). When SMTP isn't configured the caller
    is expected to log enough context that a superadmin can
    retrieve the link manually.
    """
    from app import User

    host = os.environ.get("SMTP_HOST")
    user = os.environ.get("SMTP_USER")
    pw = os.environ.get("SMTP_PASS")
    now = datetime.utcnow()
    to_norm = (to_addr or "").strip().lower()
    to_domain = to_norm.split("@", 1)[1] if "@" in to_norm else ""

    # Bounce suppression: if a User row with this email got stamped
    # by a hard-bounce webhook, skip the send.
    suppressed = (
        db.query(User.id)
          .filter(
              func.lower(User.email) == to_norm,
              User.email_bounced_at.isnot(None),
          )
          .first()
    )
    if suppressed:
        last_attempt.update({
            "status": "suppressed",
            "error": f"{to_norm} is on the bounce suppression list",
            "when": now,
            "last_to_domain": to_domain,
            "last_subject": subject,
        })
        logger.warning(
            "SMTP send suppressed (prior hard bounce) to *@%s",
            to_domain,
        )
        return False

    if not (host and user and pw):
        last_attempt.update({
            "status": "unconfigured",
            "error": "SMTP env vars not set",
            "when": now,
            "last_to_domain": to_domain,
            "last_subject": subject,
        })
        return False

    port = int(os.environ.get("SMTP_PORT", "587"))
    sender = os.environ.get("SMTP_FROM", user)
    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = to_addr
    msg["Subject"] = subject
    msg.set_content(body)
    if html:
        msg.add_alternative(html, subtype="html")
    try:
        with smtplib.SMTP(host, port, timeout=15) as s:
            s.starttls()
            s.login(user, pw)
            s.send_message(msg)
        last_attempt.update({
            "status": "sent",
            "error": "",
            "when": now,
            "last_to_domain": to_domain,
            "last_subject": subject,
        })
        return True
    except Exception as e:
        # Cheap type + message — enough for the superadmin to see
        # whether the auth creds are wrong, the host is unreachable,
        # etc. — without dumping a traceback into the HTML.
        err = f"{type(e).__name__}: {e}"
        logger.warning(
            "SMTP send failed to %s: %s",
            to_domain or "(no-to)", err,
        )
        last_attempt.update({
            "status": "failed",
            "error": err,
            "when": now,
            "last_to_domain": to_domain,
            "last_subject": subject,
        })
        return False


def health_check(db: Session) -> dict:
    """Return a dict describing email-delivery state.

    Matches the shape of `stripe_health_check` so the template
    stays symmetric. Doesn't do a live SMTP probe — reads
    `last_attempt` (updated on every send) and joins delivery-
    event totals from `EmailEvent` (updated by the Resend webhook).
    """
    from app import EmailEvent, User

    env = {
        "host":           bool(os.environ.get("SMTP_HOST")),
        "user":           bool(os.environ.get("SMTP_USER")),
        "password":       bool(os.environ.get("SMTP_PASS")),
        "from":           bool(os.environ.get("SMTP_FROM")),
        "webhook_secret": bool(os.environ.get("RESEND_WEBHOOK_SECRET")),
    }
    configured = env["host"] and env["user"] and env["password"]

    # Event totals over the last 7 days — a quick signal that:
    #   - the webhook is wired (any events at all)
    #   - bounce/complaint rate is under the ~2% Resend flags
    # Safe to run every Overview load; indexed on created_at.
    recent_events = {
        "delivered": 0, "bounced": 0, "complained": 0,
        "sent": 0, "opened": 0, "clicked": 0,
    }
    suppressed_count = 0
    last_event_at = None
    try:
        since = datetime.utcnow() - timedelta(days=7)
        rows = (
            db.query(EmailEvent.event_type, func.count(EmailEvent.id))
              .filter(EmailEvent.created_at >= since)
              .group_by(EmailEvent.event_type)
              .all()
        )
        for t, n in rows:
            # event_type comes in as "email.delivered" etc.
            key = t.split(".", 1)[-1] if "." in t else t
            if key in recent_events:
                recent_events[key] = n
        latest = db.query(func.max(EmailEvent.created_at)).scalar()
        last_event_at = latest
        suppressed_count = (
            db.query(User)
              .filter(User.email_bounced_at.isnot(None))
              .count()
        )
    except Exception:
        # EmailEvent / User columns may not exist on a pristine
        # test DB between migrations; don't blow up the Overview.
        pass

    return {
        "env":              env,
        "configured":       configured,
        "status":           last_attempt["status"],
        "error":            last_attempt["error"],
        "when":             last_attempt["when"],
        "last_to_domain":   last_attempt["last_to_domain"],
        "last_subject":     last_attempt["last_subject"],
        "recent_events":    recent_events,
        "last_event_at":    last_event_at,
        "suppressed_count": suppressed_count,
    }
