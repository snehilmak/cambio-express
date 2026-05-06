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
from api.Modules.Billing.Services.config import (
    stripe_is_configured,
    stripe_mode,
    stripe_publishable_key,
)
from api.Modules.Billing.Services.customer import ensure_stripe_customer
from api.Modules.Billing.Services.feature_flags import (
    store_feature_enabled,
    store_has_addon,
)
from api.Modules.Billing.Services.health import check_stripe_integration
from api.Modules.Billing.Services.portal import (
    NoBillingCustomerError,
    create_billing_portal_session,
)
from api.Modules.Billing.Services.referrals import (
    REFERRAL_REFEREE_CENTS,
    REFERRAL_SELF_CENTS,
    apply_pending_referral_credits,
    ensure_referral_code,
    lookup_referral_code,
    new_referral_code,
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
    handle_stripe_event,
    verify_webhook_signature,
)

__all__ = [
    "BillingError",
    "DEFAULT_RETENTION_DAYS",
    "EXPIRING_SOON_THRESHOLD_DAYS",
    "InvalidPlanError",
    "InvalidWebhookSignatureError",
    "NoBillingCustomerError",
    "REFERRAL_REFEREE_CENTS",
    "REFERRAL_SELF_CENTS",
    "StripeServiceError",
    "apply_pending_referral_credits",
    "apply_subscription_cancelled",
    "check_stripe_integration",
    "clear_cancellation_state",
    "create_billing_portal_session",
    "create_checkout_session",
    "data_retention_days_left",
    "derive_plan_from_price",
    "ensure_referral_code",
    "ensure_stripe_customer",
    "find_store_by_subscription_id",
    "get_trial_status",
    "handle_stripe_event",
    "lookup_referral_code",
    "new_referral_code",
    "resolve_price_ids",
    "store_addon_keys",
    "store_feature_enabled",
    "store_has_addon",
    "store_has_paid_plan",
    "stripe_is_configured",
    "stripe_mode",
    "stripe_publishable_key",
    "verify_webhook_signature",
]
