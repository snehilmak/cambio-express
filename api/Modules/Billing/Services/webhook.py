"""Stripe webhook signature verification + event-shape helpers.

The Flask `/webhooks/stripe` route now delegates almost everything
to this module:
  - `verify_webhook_signature` — pure HMAC + JSON parse.
  - `derive_plan_from_price`   — Price ID → (plan, billing_cycle).
  - `handle_stripe_event`      — dispatch + per-event side-effects
                                 across Billing.Services.

The route keeps the HTTP request/response wiring + the
`WebhookEvent` log-row writes (those are HTTP-facing concerns —
the route owns the response status, the Service owns the
business logic).
"""
import logging

import stripe
from sqlalchemy.orm import Session

from api.Modules.Billing.Models import Store
from api.Modules.Billing.Services.cancellation import (
    DEFAULT_RETENTION_DAYS,
    apply_subscription_cancelled,
    clear_cancellation_state,
    find_store_by_subscription_id,
)
from api.Modules.Billing.Services.checkout import resolve_price_ids
from api.Modules.Billing.Services.referrals import (
    apply_pending_referral_credits,
    ensure_referral_code,
)
from typing import Any


logger = logging.getLogger(__name__)


class InvalidWebhookSignatureError(Exception):
    """Stripe rejected the payload signature OR the JSON couldn't
    parse. Caller logs the delivery as `signature_err` and 400s."""


def verify_webhook_signature(
    payload: bytes, sig_header: str, secret: str,
) -> dict[str, Any]:
    """Verify the Stripe-Signature header against `payload` using
    `secret`. Returns the parsed event (dict). Raises
    InvalidWebhookSignatureError when the signature doesn't match
    or the body isn't valid JSON.

    The underlying Stripe / ValueError exception is preserved on
    `__cause__` for logging.
    """
    if not secret:
        raise InvalidWebhookSignatureError("Webhook secret not configured")
    try:
        return stripe.Webhook.construct_event(payload, sig_header, secret)
    except (ValueError, stripe.error.SignatureVerificationError) as e:
        raise InvalidWebhookSignatureError(str(e)) from e


def derive_plan_from_price(
    price_id: str,
) -> tuple[str, str]:
    """Map a Stripe Price ID to `(plan, billing_cycle)`.

    Plan tier:
      basic / basic_yearly → "basic"
      pro / pro_yearly     → "pro"
      anything else        → "pro" (safer fallback than "inactive";
                                    granted features the user paid for)

    Billing cycle:
      basic_yearly / pro_yearly → "yearly"
      everything else            → "monthly"

    Both fields are derived from the same Price ID lookup so they
    can't drift between the plan flip and the cycle flip.
    """
    prices = resolve_price_ids()
    basic_ids = {prices["basic"], prices["basic_yearly"]} - {""}
    yearly_ids = {prices["basic_yearly"], prices["pro_yearly"]} - {""}
    plan = "basic" if price_id in basic_ids else "pro"
    cycle = "yearly" if price_id in yearly_ids else "monthly"
    return plan, cycle


def handle_stripe_event(
    db: Session, event: dict[str, Any], *,
    retention_days: int = DEFAULT_RETENTION_DAYS,
) -> None:
    """Dispatch a verified Stripe event to the right per-event
    flow. Mutates the DB; commits.

    Handled events:
      - `checkout.session.completed`:
          flip the referee store onto its new plan, store Stripe
          customer/subscription IDs, clear any cancellation state,
          mint the store's own referral code, and apply pending
          referee credits if the store was referred.
      - `customer.subscription.deleted`:
          mark the store inactive + start the retention countdown.

    Anything else is a no-op (Stripe still gets a 200 from the
    route — that's fine, we log it as "ok" upstream).

    The function deliberately swallows referral-side errors and
    Subscription.retrieve failures so a single non-critical
    Stripe glitch can't roll back the plan flip itself.

    Raises any other exception so the caller can log it as
    `processing_err` on the WebhookEvent row.
    """
    event_type = event.get("type", "")

    if event_type == "checkout.session.completed":
        _handle_checkout_session_completed(db, event)
    elif event_type == "customer.subscription.deleted":
        _handle_subscription_deleted(db, event, retention_days=retention_days)
    # Other event types: accepted by the route, no-op here.


def _handle_checkout_session_completed(
    db: Session, event: dict[str, Any],
) -> None:
    """Returning customer or first-time checkout completed: flip
    the store onto the paid plan, persist Stripe IDs, clear any
    retention timer, run the referral flow."""
    obj = event["data"]["object"]
    store_id = obj.get("metadata", {}).get("store_id")
    if not store_id:
        return
    store = db.get(Store, int(store_id))
    if store is None:
        return

    sub_id = obj.get("subscription", "")
    customer_id = obj.get("customer", "")

    # Plan + billing-cycle: prefer the Subscription's actual price
    # ID, fall back to "pro / monthly" if Stripe is unreachable so
    # the user isn't locked out for an outage.
    try:
        sub = stripe.Subscription.retrieve(sub_id)
        price_id = sub["items"]["data"][0]["price"]["id"]
        store.plan, store.billing_cycle = derive_plan_from_price(price_id)
    except Exception as e:
        logger.error("Stripe sub retrieve error: %s", e)
        store.plan = "pro"
        store.billing_cycle = "monthly"

    store.stripe_customer_id = customer_id
    store.stripe_subscription_id = sub_id

    # Returning customer: clear cancellation + retention timer +
    # trial-reminder dedup flag. Idempotent on first-time
    # subscribers.
    clear_cancellation_state(store)

    # Referral flow: mint the referrer's own code so they get the
    # topbar crown immediately, and apply any pending referee
    # credit from the code they signed up with. Wrapped because a
    # referral hiccup must NEVER block the plan flip.
    try:
        ensure_referral_code(db, store)
        apply_pending_referral_credits(db, store)
    except Exception as e:
        logger.warning("referral hook error for store %s: %s", store.id, e)

    db.commit()


def _handle_subscription_deleted(
    db: Session, event: dict[str, Any], *, retention_days: int,
) -> None:
    """Subscription cancellation: mark the store inactive, set the
    retention countdown."""
    sub_id = event["data"]["object"].get("id", "")
    store = find_store_by_subscription_id(db, sub_id)
    if store is None:
        return
    apply_subscription_cancelled(store, retention_days=retention_days)
    db.commit()
