"""Stripe Checkout Session creation.

Pure-function helpers around the Stripe SDK so the Flask
`/subscribe/checkout` route shrinks to URL building + redirect.

The webhook (`checkout.session.completed`) is what actually flips
the store onto a paid plan — this Service only initiates the
payment flow.

Per CLAUDE.md invariant #8: `allow_promotion_codes=True` MUST be
passed to `stripe.checkout.Session.create` so customers can redeem
discount codes. Don't remove that flag without coordinating with
billing.
"""
import os

import stripe

from api.Modules.Billing.Models import Store


# Plan slugs the Service accepts. Maps to env vars holding the
# Stripe Price IDs. `_yearly` variants are billing-cadence copies
# of the same Store.plan tier (basic / pro), so the webhook flips
# Store.plan to the base name without the `_yearly` suffix.
_PLAN_ENV: dict[str, str] = {
    "basic":        "STRIPE_BASIC_PRICE_ID",
    "basic_yearly": "STRIPE_BASIC_YEARLY_PRICE_ID",
    "pro":          "STRIPE_PRO_PRICE_ID",
    "pro_yearly":   "STRIPE_PRO_YEARLY_PRICE_ID",
}


class BillingError(Exception):
    """Base class for billing-flow failures the Controller surfaces
    to the user as a flash + redirect."""


class InvalidPlanError(BillingError):
    """Plan slug isn't recognised (or its Stripe Price ID isn't
    configured in the environment)."""


class StripeServiceError(BillingError):
    """Stripe SDK raised a `StripeError`. The Controller logs the
    underlying exception + flashes a generic "try again" string."""


def resolve_price_ids() -> dict[str, str]:
    """Return `{plan_key: price_id}` for all four plan tiers. Empty
    string when an env var is unset — call sites use that to hide
    yearly buttons on the pricing page when those Price IDs aren't
    configured. Mirrors the legacy `_stripe_price_ids()` helper."""
    return {
        slug: os.environ.get(env_var, "") for slug, env_var in _PLAN_ENV.items()
    }


def create_checkout_session(
    store: Store, *, plan: str,
    success_url: str, cancel_url: str,
) -> str:
    """Create a Stripe Checkout Session for `(store, plan)` and
    return the redirect URL.

    Raises:
        StripeNotConfiguredError — `stripe.api_key` is empty
            (operator hasn't set STRIPE_SECRET_KEY).  Distinct
            from StripeServiceError so callers can render a
            clear "Stripe isn't configured" message.
        InvalidPlanError — plan slug unknown, OR the Price ID env
            var is empty (treated as "plan not offered here").
        StripeServiceError — `stripe.error.StripeError` from the
            SDK; the original exception is set as `__cause__`.

    Caller is responsible for the `allow_promotion_codes=True`
    contract — this helper sets it unconditionally per CLAUDE.md
    invariant #8.
    """
    from api.Modules.Billing.Services.config import require_stripe_configured
    require_stripe_configured()
    price_map = resolve_price_ids()
    if plan not in price_map or not price_map[plan]:
        raise InvalidPlanError(f"Plan {plan!r} is not offered here.")

    kwargs = dict(
        mode="subscription",
        line_items=[{"price": price_map[plan], "quantity": 1}],
        metadata={"store_id": str(store.id)},
        success_url=success_url,
        cancel_url=cancel_url,
        # CLAUDE.md invariant #8: discount-code field on Stripe checkout.
        allow_promotion_codes=True,
    )
    if store.stripe_customer_id:
        kwargs["customer"] = store.stripe_customer_id

    try:
        session = stripe.checkout.Session.create(**kwargs)
    except stripe.error.StripeError as e:
        raise StripeServiceError("Stripe Checkout creation failed") from e
    return session.url
