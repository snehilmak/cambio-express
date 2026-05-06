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
from api.Modules.Billing.Services.cancellation import (
    DEFAULT_RETENTION_DAYS,
    apply_subscription_cancelled,
    clear_cancellation_state,
    find_store_by_subscription_id,
)
from api.Modules.Billing.Services.feature_flags import (
    store_feature_enabled,
    store_has_addon,
)
from api.Modules.Billing.Services.portal import (
    NoBillingCustomerError,
    create_billing_portal_session,
)
from api.Modules.Billing.Services.store_state import (
    data_retention_days_left,
    store_addon_keys,
    store_has_paid_plan,
)
from api.Modules.Billing.Services.trial import (
    EXPIRING_SOON_THRESHOLD_DAYS,
    get_trial_status,
)
from api.Modules.Billing.Services.webhook import (
    InvalidWebhookSignatureError,
    derive_plan_from_price,
    verify_webhook_signature,
)

__all__ = [
    "BillingError",
    "DEFAULT_RETENTION_DAYS",
    "EXPIRING_SOON_THRESHOLD_DAYS",
    "InvalidPlanError",
    "InvalidWebhookSignatureError",
    "NoBillingCustomerError",
    "StripeServiceError",
    "apply_subscription_cancelled",
    "clear_cancellation_state",
    "create_billing_portal_session",
    "create_checkout_session",
    "data_retention_days_left",
    "derive_plan_from_price",
    "find_store_by_subscription_id",
    "get_trial_status",
    "resolve_price_ids",
    "store_addon_keys",
    "store_feature_enabled",
    "store_has_addon",
    "store_has_paid_plan",
    "verify_webhook_signature",
]
