"""Webhooks — Models.

Two classes log inbound webhook deliveries:

* ``WebhookEvent`` — every POST to /webhooks/stripe (success,
                     no-op, or signature failure) so the Webhook
                     Health report can show recent traffic.
* ``EmailEvent``   — delivery-status events from Resend's webhook
                     (sent / delivered / bounced / complained /
                     opened / clicked).
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text

from api.Core.Database import Base


class WebhookEvent(Base):
    """Inbound Stripe webhook log. Every delivery to
    ``/webhooks/stripe`` inserts one row — successful, no-op, or
    signature-failed — so the Webhook Health report can show recent
    deliveries + failure rate without round-tripping the Stripe API.
    """

    __tablename__ = "webhook_event"
    id           = Column(Integer, primary_key=True)
    received_at  = Column(DateTime, default=datetime.utcnow,
                           nullable=False, index=True)
    source       = Column(String(20), default="stripe", nullable=False)
    event_id     = Column(String(80), default="")          # stripe evt_...
    event_type   = Column(String(80), default="", index=True)
    status       = Column(String(20), default="ok",
                           nullable=False, index=True)
    # ok            — verified + handled (or accepted no-op)
    # signature_err — bad signature, payload rejected
    # processing_err — verified but raised inside handler
    error        = Column(Text, default="")


class EmailEvent(Base):
    """A delivery-status event posted to us by Resend's webhook.

    One row per event — Resend sends one-per-recipient events even
    for multipart sends, so a single ``_send_email()`` call that
    goes to N addresses produces N email.delivered events (or
    .bounced, .complained, .opened, .clicked).

    ``user_id`` is best-effort — we match the recipient address
    against ``User.email`` at webhook time. It can be NULL for
    addresses we've removed (purged user) or never matched
    (superadmin test email to a personal address, for example).

    ``payload`` is the raw JSON Resend sent us, in case we want to
    mine it later for fields we didn't parse out (the provider adds
    fields over time). Size-bounded to 8KB to keep runaway events
    from ballooning the table.
    """

    __tablename__ = "email_event"
    id           = Column(Integer, primary_key=True)
    # Resend's provider-side message id. Same message_id will have
    # multiple events over its lifecycle (sent → delivered → opened
    # → …).
    message_id   = Column(String(80), default="", index=True)
    # The normalized to-address (lowercased, trimmed) the event is
    # about.
    to_addr      = Column(String(255), default="", index=True)
    user_id      = Column(Integer, ForeignKey("user.id"), nullable=True)
    # "email.sent" | "email.delivered" | "email.bounced" |
    # "email.complained" | "email.opened" | "email.clicked" |
    # "email.delivery_delayed"
    event_type   = Column(String(40), nullable=False, index=True)
    # For bounces: "hard" | "soft". Empty string for non-bounce
    # events.
    bounce_type  = Column(String(16), default="")
    payload      = Column(Text, default="")
    created_at   = Column(DateTime, default=datetime.utcnow, index=True)


__all__ = ["EmailEvent", "WebhookEvent"]
