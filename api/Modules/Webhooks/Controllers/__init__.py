"""Webhook receivers (Stripe + Resend).

Migrated from Flask's ``@app.route("/webhooks/...")`` handlers in
chunk-Later. Both routes are intentionally CSRF-exempt (they
authenticate via signature headers, not session cookies).

Public contract:

  POST /webhooks/stripe   verify Stripe-Signature → dispatch
                           ``api.Modules.Billing.Services.handle_stripe_event``
  POST /webhooks/resend   verify Svix signature → record EmailEvent +
                           flip suppression flags on hard bounces /
                           complaints

The asgi entrypoint (asgi.py) routes ``/webhooks/*`` directly to
this FastAPI app, so the public URLs Stripe + Resend point at don't
change. ``/api/v2/webhooks/*`` works too (dispatcher prefix-strip).
"""
from __future__ import annotations

import json
import os
from datetime import datetime

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from api.Core.Database import get_db
from api.Core.RateLimit import limiter as _rate_limiter


router = APIRouter()


# Signature verification (Stripe-Signature / Svix) is the real auth
# defense here, but without a flood ceiling an attacker can spray
# invalid-signature requests, each of which still writes a
# WebhookEvent / EmailEvent row and burns a DB connection. 120/min
# per IP (BACKLOG D6) sits well above Stripe's + Resend's real
# delivery + retry cadence so legitimate traffic never trips it.
@router.post("/resend")
@_rate_limiter.limit("120/minute")
async def resend_webhook(request: Request, db: Session = Depends(get_db)):
    """Resend delivery-event receiver — svix-signature verified.

    Records one ``EmailEvent`` row per (event, recipient) tuple,
    then applies side effects:

      * ``email.bounced`` with ``bounce.type=hard``  → suppress
      * ``email.complained``                         → suppress
        + flip every ``notify_*`` toggle off on the User row
    """
    from api.Modules.Tenancy.Models import User
    from api.Modules.Webhooks.Models import EmailEvent
    from api.Modules.Webhooks.Services import (
        apply_resend_side_effects,
        verify_resend_signature,
    )

    secret = os.environ.get("RESEND_WEBHOOK_SECRET", "")
    raw = await request.body()
    svix_id        = request.headers.get("svix-id", "")
    svix_timestamp = request.headers.get("svix-timestamp", "")
    svix_signature = request.headers.get("svix-signature", "")
    if not verify_resend_signature(secret, svix_id, svix_timestamp,
                                    svix_signature, raw):
        return JSONResponse({"error": "Invalid signature"}, status_code=400)

    try:
        event = json.loads(raw or b"{}")
    except Exception:
        return JSONResponse({"error": "Invalid JSON"}, status_code=400)

    event_type = (event or {}).get("type", "") or ""
    data = (event or {}).get("data", {}) or {}
    message_id = data.get("email_id") or ""
    bounce_type = ""
    if isinstance(data.get("bounce"), dict):
        bounce_type = data["bounce"].get("type", "") or ""
    recipients = data.get("to") or []
    if isinstance(recipients, str):
        recipients = [recipients]

    payload_json = ""
    try:
        payload_json = json.dumps(event)[:8000]
    except Exception:
        payload_json = ""

    from sqlalchemy import func
    for raw_to in recipients:
        to_norm = (raw_to or "").strip().lower()
        user_id = None
        if to_norm:
            matched = (db.query(User.id)
                       .filter(func.lower(User.email) == to_norm)
                       .first())
            user_id = matched[0] if matched else None
        db.add(EmailEvent(
            message_id=message_id[:80], to_addr=to_norm[:255],
            user_id=user_id, event_type=event_type[:40],
            bounce_type=bounce_type[:16], payload=payload_json,
        ))
        apply_resend_side_effects(db, event_type, to_norm, bounce_type)
    db.commit()
    return {"ok": True}


@router.post("/stripe")
@_rate_limiter.limit("120/minute")
async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
    """Stripe webhook receiver — signature verified.

    Persists every delivery (verified or not) so the Webhook Health
    report has data, then dispatches to
    ``handle_stripe_event``. Returns 200 even on handler errors so
    Stripe doesn't retry-storm a buggy handler — operator sees the
    failure rate via the Webhook Health page.
    """
    from api.Core.Database import SessionLocal
    from api.Modules.Webhooks.Models import WebhookEvent
    from api.Modules.Billing.Services import (
        DEFAULT_RETENTION_DAYS as DATA_RETENTION_DAYS,
        InvalidWebhookSignatureError,
        handle_stripe_event,
        verify_webhook_signature,
    )

    payload = await request.body()
    sig_header = request.headers.get("Stripe-Signature", "")
    webhook_secret = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
    try:
        event = verify_webhook_signature(payload, sig_header, webhook_secret)
    except InvalidWebhookSignatureError as e:
        with SessionLocal() as session:
            try:
                session.add(WebhookEvent(
                    source="stripe", status="signature_err",
                    error=str(e)[:500]))
                session.commit()
            except Exception:
                session.rollback()
        return JSONResponse({"error": "Invalid signature"}, status_code=400)

    with SessionLocal() as session:
        log_row = WebhookEvent(
            source="stripe",
            event_id=event.get("id", "") or "",
            event_type=event.get("type", "") or "",
            status="ok",
        )
        try:
            session.add(log_row)
            session.commit()
        except Exception:
            session.rollback()
            log_row = None

        try:
            handle_stripe_event(
                session, event,
                retention_days=DATA_RETENTION_DAYS,
            )
        except Exception as e:
            if log_row is not None:
                try:
                    log_row.status = "processing_err"
                    log_row.error = (str(e) or type(e).__name__)[:500]
                    session.commit()
                except Exception:
                    session.rollback()
            # Still return 200 — Stripe shouldn't retry handler bugs.
            return {"ok": True, "warning": "handler error logged"}

    return {"ok": True}
