"""Webhook-event SQL helpers (email events from Resend, etc.).

The email log + bounce dashboard read these rows. Writes happen
in ``api/Modules/Webhooks/Controllers`` (signature-verified
ingestion).
"""
from sqlalchemy.orm import Query, Session

from api.Modules.Webhooks.Models import EmailEvent


def email_events_query(
    db: Session,
    *,
    search: str = "",
    event_type: str = "",
) -> "Query[EmailEvent]":
    """Base Query for the email-log table. Optional address
    substring + exact event type filter. Caller paginates."""
    query = db.query(EmailEvent)
    if search:
        query = query.filter(EmailEvent.to_addr.ilike(f"%{search}%"))
    if event_type:
        query = query.filter(EmailEvent.event_type == event_type)
    return query.order_by(EmailEvent.created_at.desc())
