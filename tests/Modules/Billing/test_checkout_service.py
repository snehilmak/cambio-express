"""Unit tests for Billing.Services.checkout (PR 43)."""
import os
from unittest.mock import MagicMock, patch

import pytest
import stripe


# ── resolve_price_ids ───────────────────────────────────────


def test_resolve_price_ids_reads_env(monkeypatch):
    from api.Modules.Billing.Services import resolve_price_ids
    monkeypatch.setenv("STRIPE_BASIC_PRICE_ID", "price_basic_x")
    monkeypatch.setenv("STRIPE_PRO_PRICE_ID", "price_pro_x")
    monkeypatch.setenv("STRIPE_BASIC_YEARLY_PRICE_ID", "price_basic_year")
    monkeypatch.setenv("STRIPE_PRO_YEARLY_PRICE_ID", "price_pro_year")
    ids = resolve_price_ids()
    assert ids == {
        "basic":        "price_basic_x",
        "basic_yearly": "price_basic_year",
        "pro":          "price_pro_x",
        "pro_yearly":   "price_pro_year",
    }


def test_resolve_price_ids_unset_defaults_to_empty(monkeypatch):
    """Unset env vars yield empty strings — call sites use that to
    hide yearly buttons when the Price IDs aren't configured."""
    from api.Modules.Billing.Services import resolve_price_ids
    monkeypatch.delenv("STRIPE_BASIC_YEARLY_PRICE_ID", raising=False)
    monkeypatch.delenv("STRIPE_PRO_YEARLY_PRICE_ID", raising=False)
    ids = resolve_price_ids()
    assert ids["basic_yearly"] == ""
    assert ids["pro_yearly"] == ""


# ── create_checkout_session ─────────────────────────────────


def _store(*, customer_id=None):
    """Stand-in store object — only the attributes the Service reads."""
    s = MagicMock()
    s.id = 99
    s.stripe_customer_id = customer_id
    return s


def test_create_checkout_session_rejects_unknown_plan(test_store_id):
    from api.Modules.Billing.Services import (
        InvalidPlanError, create_checkout_session,
    )
    with pytest.raises(InvalidPlanError):
        create_checkout_session(
            _store(), plan="garbage",
            success_url="https://x", cancel_url="https://y",
        )


def test_create_checkout_session_rejects_plan_with_empty_price_id(monkeypatch):
    """Plan slug exists in the map but env var is empty — same
    InvalidPlanError as a fully unknown slug."""
    from api.Modules.Billing.Services import (
        InvalidPlanError, create_checkout_session,
    )
    monkeypatch.setenv("STRIPE_BASIC_YEARLY_PRICE_ID", "")
    with pytest.raises(InvalidPlanError):
        create_checkout_session(
            _store(), plan="basic_yearly",
            success_url="https://x", cancel_url="https://y",
        )


def test_create_checkout_session_returns_url_on_success(monkeypatch):
    from api.Modules.Billing.Services import create_checkout_session
    monkeypatch.setenv("STRIPE_BASIC_PRICE_ID", "price_basic_x")
    fake_session = MagicMock(url="https://checkout.stripe.com/abc")
    with patch.object(
        stripe.checkout.Session, "create", return_value=fake_session,
    ) as create_call:
        url = create_checkout_session(
            _store(), plan="basic",
            success_url="https://success", cancel_url="https://cancel",
        )
    assert url == "https://checkout.stripe.com/abc"
    # Verify the kwargs Stripe was called with
    kwargs = create_call.call_args.kwargs
    assert kwargs["mode"] == "subscription"
    assert kwargs["line_items"] == [
        {"price": "price_basic_x", "quantity": 1},
    ]
    assert kwargs["metadata"] == {"store_id": "99"}
    assert kwargs["success_url"] == "https://success"
    assert kwargs["cancel_url"] == "https://cancel"
    # CLAUDE.md invariant #8 — discount codes must be enabled
    assert kwargs["allow_promotion_codes"] is True


def test_create_checkout_session_passes_existing_customer(monkeypatch):
    """When the store already has a stripe_customer_id, we attach it
    so the Stripe checkout pre-fills the billing card on file."""
    from api.Modules.Billing.Services import create_checkout_session
    monkeypatch.setenv("STRIPE_BASIC_PRICE_ID", "price_basic_x")
    fake_session = MagicMock(url="https://checkout.stripe.com/abc")
    with patch.object(
        stripe.checkout.Session, "create", return_value=fake_session,
    ) as create_call:
        create_checkout_session(
            _store(customer_id="cus_existing"),
            plan="basic",
            success_url="https://x", cancel_url="https://y",
        )
    assert create_call.call_args.kwargs["customer"] == "cus_existing"


def test_create_checkout_session_omits_customer_when_no_id(monkeypatch):
    from api.Modules.Billing.Services import create_checkout_session
    monkeypatch.setenv("STRIPE_BASIC_PRICE_ID", "price_basic_x")
    fake_session = MagicMock(url="https://x")
    with patch.object(
        stripe.checkout.Session, "create", return_value=fake_session,
    ) as create_call:
        create_checkout_session(
            _store(customer_id=None),
            plan="basic",
            success_url="https://x", cancel_url="https://y",
        )
    assert "customer" not in create_call.call_args.kwargs


def test_create_checkout_session_wraps_stripe_error(monkeypatch):
    from api.Modules.Billing.Services import (
        StripeServiceError, create_checkout_session,
    )
    monkeypatch.setenv("STRIPE_BASIC_PRICE_ID", "price_basic_x")
    underlying = stripe.error.StripeError("network down")
    with patch.object(
        stripe.checkout.Session, "create", side_effect=underlying,
    ):
        with pytest.raises(StripeServiceError) as exc:
            create_checkout_session(
                _store(), plan="basic",
                success_url="https://x", cancel_url="https://y",
            )
    # Original Stripe error is set as __cause__ for logging
    assert exc.value.__cause__ is underlying


def test_create_checkout_session_supports_yearly_plans(monkeypatch):
    """Yearly variants land on the same Store.plan tier (basic / pro)
    but use distinct Stripe Price IDs."""
    from api.Modules.Billing.Services import create_checkout_session
    monkeypatch.setenv("STRIPE_PRO_YEARLY_PRICE_ID", "price_pro_year")
    fake_session = MagicMock(url="https://x")
    with patch.object(
        stripe.checkout.Session, "create", return_value=fake_session,
    ) as create_call:
        create_checkout_session(
            _store(), plan="pro_yearly",
            success_url="https://x", cancel_url="https://y",
        )
    assert create_call.call_args.kwargs["line_items"] == [
        {"price": "price_pro_year", "quantity": 1},
    ]
