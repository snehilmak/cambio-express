"""Billing — Services. Stripe Checkout + billing-portal +
subscription-state business logic, lifted out of app.py during the
Auth/Billing slice of the strangler-fig migration.
"""
from api.Modules.Billing.Services.checkout import (
    BillingError,
    InvalidPlanError,
    StripeServiceError,
    create_checkout_session,
    resolve_price_ids,
)
from api.Modules.Billing.Services.portal import (
    NoBillingCustomerError,
    create_billing_portal_session,
)
from api.Modules.Billing.Services.webhook import (
    InvalidWebhookSignatureError,
    derive_plan_from_price,
    verify_webhook_signature,
)

__all__ = [
    "BillingError",
    "InvalidPlanError",
    "InvalidWebhookSignatureError",
    "NoBillingCustomerError",
    "StripeServiceError",
    "create_billing_portal_session",
    "create_checkout_session",
    "derive_plan_from_price",
    "resolve_price_ids",
    "verify_webhook_signature",
]
