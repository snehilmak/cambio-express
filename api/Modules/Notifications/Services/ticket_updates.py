"""Support-ticket update notifications.

Two directions, mirroring who acted on the ticket:

  - **Staff acted** (superadmin replied / changed status) →
    ``send_ticket_update_to_user`` emails + pushes the person who
    filed the ticket, gated on their ``notify_ticket_updates`` /
    ``notify_ticket_updates_push`` preferences.
  - **Store side acted** (new ticket, user reply, reopen) →
    ``send_ticket_event_to_platform`` emails every active
    platform recipient. Today that's superadmins only; the
    planned "support" platform role widens the recipient query
    here (single place to touch).

Both are worker entry-points for the D5 enqueue pattern
(``api.Core.Jobs.enqueue``): top-level functions, primitive args
only, each opens its own ``SessionLocal`` because the request
session is closed by the time an async worker runs. Callers fire
them AFTER committing the ticket mutation so the worker sees the
new state.

Everything is best-effort — a notification failure must never
fail the ticket mutation that triggered it.
"""
from __future__ import annotations

import logging
import os

from sqlalchemy.orm import Session


_log = logging.getLogger(__name__)


# Event codes → human phrasing. ``detail`` carries the variable
# part (new status, reply snippet) so workers stay primitive-args.
_USER_EVENT_LABEL = {
    "staff_reply":   "Support replied to your ticket",
    "status_change": "Your ticket's status changed",
}

_PLATFORM_EVENT_LABEL = {
    "created":    "New ticket",
    "user_reply": "New reply",
    "reopened":   "Ticket reopened",
}


USER_SUBJECT = "Update on your support ticket: {subject}"
PLATFORM_SUBJECT = "Ticket #{ticket_id} {store_name}: {event_label}"


USER_BODY = """\
Hi {name},

{event_line} — "{subject}" (ticket #{ticket_id}).

{detail_block}Open the conversation in DineroBook:
    {view_url}

You're getting this because you filed the ticket. Turn ticket
updates off on your notifications page:
    {notifications_url}

— DineroBook
"""

PLATFORM_BODY = """\
{event_label} on ticket #{ticket_id} — "{subject}"
Store: {store_name}
From: {actor_name}
Status: {status} · Priority: {priority}

{detail_block}Open the ticket queue:
    {view_url}

— DineroBook
"""


def _base_url() -> str:
    return (
        os.environ.get("APP_BASE_URL") or "https://dinerobook.com"
    ).rstrip("/")


def _render_html(
    *, heading: str, event_line: str, ticket: object, store_name: str,
    detail: str, view_url: str, cta_label: str,
    notifications_url: str | None, name: str,
) -> str | None:
    """Render the shared ticket-update email chrome. Returns None on
    template failure so callers fall back to plaintext-only."""
    from api.Core.Clock import utc_now
    from api.Modules.Notifications.Services.templates import (
        render_email_template,
    )
    try:
        return render_email_template(
            "emails/ticket_update.html",
            preheader=event_line,
            heading=heading,
            event_line=event_line,
            name=name,
            ticket_id=getattr(ticket, "id", ""),
            subject=getattr(ticket, "subject", "") or "",
            store_name=store_name,
            status=(getattr(ticket, "status", "") or "open").replace("_", " "),
            priority=getattr(ticket, "priority", "") or "normal",
            detail=detail,
            view_url=view_url,
            cta_label=cta_label,
            notifications_url=notifications_url,
            year=utc_now().year,
            base_url=_base_url(),
        )
    except Exception:  # pragma: no cover — template path
        _log.exception("ticket-update: template render failed")
        return None


def _deliver(
    db: Session, user: object, subject: str, body: str, html: str | None,
) -> int:
    """Send one email, best-effort. Returns 1 on an attempted send."""
    from api.Modules.Notifications.Services.smtp import send_email
    try:
        send_email(db, user.email, subject, body, html)  # type: ignore[attr-defined]
        return 1
    except Exception:  # pragma: no cover — best-effort SMTP
        _log.exception(
            "ticket-update: send_email failed for user_id=%s",
            getattr(user, "id", None),
        )
        return 0


def send_ticket_update_to_user(
    ticket_id: int, event: str, detail: str = "",
) -> int:
    """Notify the ticket's creator that staff acted on it.

    ``event`` ∈ ``_USER_EVENT_LABEL``; ``detail`` carries the new
    status or a snippet of the staff reply. Returns emails attempted
    (0 or 1). Push fans out independently of the email gate — the
    two channels have separate toggles.
    """
    from api.Core.Database import SessionLocal
    from api.Modules.Tenancy.Models import User
    from api.Modules.Support.Models import SupportTicket

    event_line = _USER_EVENT_LABEL.get(event, "Your ticket was updated")
    sent = 0
    with SessionLocal() as db:
        ticket = db.get(SupportTicket, ticket_id)
        if ticket is None or ticket.user_id is None:
            return 0
        user = db.get(User, ticket.user_id)
        if user is None or not user.is_active:
            return 0

        view_url = f"{_base_url()}/app/account/tickets"
        notifications_url = f"{_base_url()}/app/account/notifications"
        name = user.full_name or user.username or ""
        subject = USER_SUBJECT.format(subject=ticket.subject or "")
        detail_block = f"{detail}\n\n" if detail else ""

        wants_email = (
            bool(user.email)
            and bool(getattr(user, "notify_ticket_updates", True))
            and user.email_bounced_at is None
        )
        if wants_email:
            body = USER_BODY.format(
                name=name,
                event_line=event_line,
                subject=ticket.subject or "",
                ticket_id=ticket.id,
                detail_block=detail_block,
                view_url=view_url,
                notifications_url=notifications_url,
            )
            html = _render_html(
                heading="Ticket update",
                event_line=event_line,
                ticket=ticket,
                store_name="",
                detail=detail,
                view_url=view_url,
                cta_label="Open the conversation",
                notifications_url=notifications_url,
                name=name,
            )
            sent += _deliver(db, user, subject, body, html)

        try:
            from api.Modules.Notifications.Services.push import (
                send_push, user_wants_push,
            )
            if user_wants_push(user, "ticket_update"):
                send_push(
                    db,
                    user_id=int(user.id),
                    title=subject,
                    body=event_line + (f" — {detail}" if detail else ""),
                    url="/app/account/tickets",
                    tag=f"ticket_update:{ticket.id}",
                )
        except Exception as exc:  # pragma: no cover — push best-effort
            _log.warning(
                "ticket-update push failed for user %s: %s", user.id, exc,
            )
    return sent


def platform_recipients(db: Session) -> list[object]:
    """Active platform users who should hear about store-side ticket
    activity: superadmins + the tickets-only "support" role."""
    from api.Modules.Tenancy.Models import User

    return (
        db.query(User)
          .filter(
              User.is_active == True,  # noqa: E712 — SQLAlchemy boolean
              User.role.in_(("superadmin", "support")),
              User.email != "",
              User.notify_ticket_updates == True,  # noqa: E712
              User.email_bounced_at.is_(None),
          )
          .all()
    )


def send_ticket_event_to_platform(
    ticket_id: int, event: str, detail: str = "", actor_name: str = "",
) -> int:
    """Notify the platform side (superadmins) of store-side ticket
    activity: a new ticket, a user reply, or a reopen.

    Returns emails attempted. No push — the platform side works the
    queue from the superadmin tickets page.
    """
    from api.Core.Database import SessionLocal
    from api.Modules.Support.Models import SupportTicket
    from api.Modules.Tenancy.Models import Store

    event_label = _PLATFORM_EVENT_LABEL.get(event, "Ticket updated")
    sent = 0
    with SessionLocal() as db:
        ticket = db.get(SupportTicket, ticket_id)
        if ticket is None:
            return 0
        store = db.get(Store, ticket.store_id)
        store_name = (store.name if store else "") or f"store #{ticket.store_id}"

        view_url = f"{_base_url()}/app/superadmin/tickets"
        subject = PLATFORM_SUBJECT.format(
            ticket_id=ticket.id, store_name=store_name,
            event_label=event_label,
        )
        detail_block = f"{detail}\n\n" if detail else ""
        body = PLATFORM_BODY.format(
            event_label=event_label,
            ticket_id=ticket.id,
            subject=ticket.subject or "",
            store_name=store_name,
            actor_name=actor_name or (ticket.submitted_by or ""),
            status=ticket.status or "open",
            priority=ticket.priority or "normal",
            detail_block=detail_block,
            view_url=view_url,
        )
        for user in platform_recipients(db):
            html = _render_html(
                heading=event_label,
                event_line=(
                    f"{event_label} from {store_name}"
                    + (f" · {actor_name}" if actor_name else "")
                ),
                ticket=ticket,
                store_name=store_name,
                detail=detail,
                view_url=view_url,
                cta_label="Open the ticket queue",
                notifications_url=None,
                name=user.full_name or user.username or "",
            )
            sent += _deliver(db, user, subject, body, html)
    return sent
