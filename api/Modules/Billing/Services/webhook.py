"""Stripe webhook signature verification + event-shape helpers.

The Flask `/webhooks/stripe` route stays in app.py (it handles
side-effects across several modules: store plan flip, referral
credits, retention timer, daily P&L) — but the signature
verification + price→plan mapping are pure functions that belong
in the Service layer.
"""
import stripe

from api.Modules.Billing.Services.checkout import resolve_price_ids


class InvalidWebhookSignatureError(Exception):
    """Stripe rejected the payload signature OR the JSON couldn't
    parse. Caller logs the delivery as `signature_err` and 400s."""


def verify_webhook_signature(
    payload: bytes, sig_header: str, secret: str,
) -> dict:
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
