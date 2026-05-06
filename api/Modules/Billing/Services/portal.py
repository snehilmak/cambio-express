"""Stripe Customer Portal Session creation.

Service-side equivalent of `_open_billing_portal` in app.py: creates
a `billing_portal.Session` for the store's existing Stripe customer
and returns the redirect URL. The Flask routes wrap the result with
flash + redirect glue.

Used by both the "Manage billing" button and the cancel flow — they
go to the same Stripe portal but the route's flash-error message
differs.
"""
import stripe

from api.Modules.Billing.Models import Store
from api.Modules.Billing.Services.checkout import StripeServiceError


class NoBillingCustomerError(Exception):
    """Store has no `stripe_customer_id` — caller must surface a
    different error message than a generic Stripe failure (typically
    "no billing account found, pick a plan first")."""


def create_billing_portal_session(
    store: Store, *, return_url: str,
) -> str:
    """Create a Stripe Customer Portal Session for `store` and return
    the redirect URL.

    Raises:
        NoBillingCustomerError — store has no `stripe_customer_id`.
            The caller's flash message should suggest picking a plan
            (which triggers the customer creation in the webhook).
        StripeServiceError — `stripe.error.StripeError` from the SDK
            (the underlying exception is on `__cause__` for logging).
    """
    if not store or not getattr(store, "stripe_customer_id", None):
        raise NoBillingCustomerError(
            "Store has no Stripe billing customer.",
        )
    try:
        portal = stripe.billing_portal.Session.create(
            customer=store.stripe_customer_id,
            return_url=return_url,
        )
    except stripe.error.StripeError as e:
        raise StripeServiceError("Stripe billing portal failed") from e
    return portal.url
