"""Unit tests for Billing.Services.portal (PR 44)."""
from unittest.mock import MagicMock, patch

import pytest
import stripe


def _store(*, customer_id=None):
    """Stand-in store object with only the attributes the Service reads."""
    s = MagicMock()
    s.id = 99
    s.stripe_customer_id = customer_id
    return s


def test_create_billing_portal_session_returns_url():
    from api.Modules.Billing.Services import (
        create_billing_portal_session,
    )
    fake = MagicMock(url="https://billing.stripe.com/session/abc")
    with patch.object(
        stripe.billing_portal.Session, "create", return_value=fake,
    ) as create_call:
        url = create_billing_portal_session(
            _store(customer_id="cus_xyz"),
            return_url="https://x/admin/subscription",
        )
    assert url == "https://billing.stripe.com/session/abc"
    kwargs = create_call.call_args.kwargs
    assert kwargs["customer"] == "cus_xyz"
    assert kwargs["return_url"] == "https://x/admin/subscription"


def test_create_billing_portal_session_no_customer_raises():
    from api.Modules.Billing.Services import (
        NoBillingCustomerError, create_billing_portal_session,
    )
    with pytest.raises(NoBillingCustomerError):
        create_billing_portal_session(
            _store(customer_id=None),
            return_url="https://x",
        )


def test_create_billing_portal_session_empty_customer_raises():
    """Empty string is treated the same as None — both surface the
    "no billing customer" error."""
    from api.Modules.Billing.Services import (
        NoBillingCustomerError, create_billing_portal_session,
    )
    with pytest.raises(NoBillingCustomerError):
        create_billing_portal_session(
            _store(customer_id=""),
            return_url="https://x",
        )


def test_create_billing_portal_session_none_store_raises():
    """A null store (no current_store()) also routes through
    NoBillingCustomerError."""
    from api.Modules.Billing.Services import (
        NoBillingCustomerError, create_billing_portal_session,
    )
    with pytest.raises(NoBillingCustomerError):
        create_billing_portal_session(None, return_url="https://x")


def test_create_billing_portal_session_wraps_stripe_error():
    from api.Modules.Billing.Services import (
        StripeServiceError, create_billing_portal_session,
    )
    underlying = stripe.error.StripeError("Stripe is down")
    with patch.object(
        stripe.billing_portal.Session, "create", side_effect=underlying,
    ):
        with pytest.raises(StripeServiceError) as exc:
            create_billing_portal_session(
                _store(customer_id="cus_xyz"),
                return_url="https://x",
            )
    assert exc.value.__cause__ is underlying
