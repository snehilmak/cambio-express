"""Webhooks module — Stripe + Resend delivery-event receivers.

Stripe and Resend POST event payloads at:

  POST /api/v2/webhooks/stripe   (also reachable at /webhooks/stripe
                                  via the asgi.py routing — no URL
                                  change visible to the providers)
  POST /api/v2/webhooks/resend   (same dual-path behavior)

The route bodies live in ``Controllers/``. Stripe + Resend signature
verification and the per-event business logic stay in their
existing places (``api.Modules.Billing.Services.handle_stripe_event``
and the helpers in ``app.py`` for now) — the controllers are thin
HTTP adapters.
"""
