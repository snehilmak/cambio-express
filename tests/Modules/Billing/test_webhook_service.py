"""Unit tests for Billing.Services.webhook (PR 45)."""
from unittest.mock import patch

import pytest
import stripe


# ── verify_webhook_signature ────────────────────────────────


def test_verify_webhook_signature_returns_event_dict():
    from api.Modules.Billing.Services import verify_webhook_signature
    fake_event = {"id": "evt_1", "type": "checkout.session.completed"}
    with patch.object(
        stripe.Webhook, "construct_event", return_value=fake_event,
    ) as call:
        out = verify_webhook_signature(b"payload", "t=1,v1=abc", "secret")
    assert out == fake_event
    args = call.call_args.args
    assert args == (b"payload", "t=1,v1=abc", "secret")


def test_verify_webhook_signature_rejects_when_secret_unset():
    from api.Modules.Billing.Services import (
        InvalidWebhookSignatureError, verify_webhook_signature,
    )
    with pytest.raises(InvalidWebhookSignatureError):
        verify_webhook_signature(b"payload", "sig", "")


def test_verify_webhook_signature_wraps_signature_error():
    from api.Modules.Billing.Services import (
        InvalidWebhookSignatureError, verify_webhook_signature,
    )
    underlying = stripe.error.SignatureVerificationError("bad sig", "sig", "header")
    with patch.object(
        stripe.Webhook, "construct_event", side_effect=underlying,
    ):
        with pytest.raises(InvalidWebhookSignatureError) as exc:
            verify_webhook_signature(b"payload", "sig", "secret")
    assert exc.value.__cause__ is underlying


def test_verify_webhook_signature_wraps_value_error():
    """Stripe raises ValueError on malformed JSON. Treated the same
    as a signature mismatch — caller logs + returns 400."""
    from api.Modules.Billing.Services import (
        InvalidWebhookSignatureError, verify_webhook_signature,
    )
    with patch.object(
        stripe.Webhook, "construct_event", side_effect=ValueError("bad json"),
    ):
        with pytest.raises(InvalidWebhookSignatureError):
            verify_webhook_signature(b"payload", "sig", "secret")


# ── derive_plan_from_price ──────────────────────────────────


def test_derive_plan_from_price_basic_monthly(monkeypatch):
    from api.Modules.Billing.Services import derive_plan_from_price
    monkeypatch.setenv("STRIPE_BASIC_PRICE_ID", "price_basic_x")
    monkeypatch.setenv("STRIPE_BASIC_YEARLY_PRICE_ID", "")
    monkeypatch.setenv("STRIPE_PRO_PRICE_ID", "price_pro_x")
    monkeypatch.setenv("STRIPE_PRO_YEARLY_PRICE_ID", "")
    plan, cycle = derive_plan_from_price("price_basic_x")
    assert plan == "basic"
    assert cycle == "monthly"


def test_derive_plan_from_price_basic_yearly(monkeypatch):
    from api.Modules.Billing.Services import derive_plan_from_price
    monkeypatch.setenv("STRIPE_BASIC_PRICE_ID", "price_basic_x")
    monkeypatch.setenv("STRIPE_BASIC_YEARLY_PRICE_ID", "price_basic_year")
    monkeypatch.setenv("STRIPE_PRO_PRICE_ID", "price_pro_x")
    monkeypatch.setenv("STRIPE_PRO_YEARLY_PRICE_ID", "price_pro_year")
    plan, cycle = derive_plan_from_price("price_basic_year")
    assert plan == "basic"
    assert cycle == "yearly"


def test_derive_plan_from_price_pro_monthly(monkeypatch):
    from api.Modules.Billing.Services import derive_plan_from_price
    monkeypatch.setenv("STRIPE_BASIC_PRICE_ID", "price_basic_x")
    monkeypatch.setenv("STRIPE_PRO_PRICE_ID", "price_pro_x")
    plan, cycle = derive_plan_from_price("price_pro_x")
    assert plan == "pro"
    assert cycle == "monthly"


def test_derive_plan_from_price_pro_yearly(monkeypatch):
    from api.Modules.Billing.Services import derive_plan_from_price
    monkeypatch.setenv("STRIPE_BASIC_PRICE_ID", "price_basic_x")
    monkeypatch.setenv("STRIPE_BASIC_YEARLY_PRICE_ID", "price_basic_year")
    monkeypatch.setenv("STRIPE_PRO_PRICE_ID", "price_pro_x")
    monkeypatch.setenv("STRIPE_PRO_YEARLY_PRICE_ID", "price_pro_year")
    plan, cycle = derive_plan_from_price("price_pro_year")
    assert plan == "pro"
    assert cycle == "yearly"


def test_derive_plan_from_price_unknown_falls_back_to_pro(monkeypatch):
    """Unknown Price ID → ("pro", "monthly"). Documented fallback —
    safer than locking the user out of features they paid for."""
    from api.Modules.Billing.Services import derive_plan_from_price
    monkeypatch.setenv("STRIPE_BASIC_PRICE_ID", "price_basic_x")
    monkeypatch.setenv("STRIPE_PRO_PRICE_ID", "price_pro_x")
    plan, cycle = derive_plan_from_price("price_unrelated_xyz")
    assert plan == "pro"
    assert cycle == "monthly"


def test_derive_plan_from_price_empty_env_safe(monkeypatch):
    """Empty env vars must NOT cause the empty string to match an
    unknown Price ID (the legacy `set - {""}` filter handles it)."""
    from api.Modules.Billing.Services import derive_plan_from_price
    monkeypatch.setenv("STRIPE_BASIC_PRICE_ID", "")
    monkeypatch.setenv("STRIPE_BASIC_YEARLY_PRICE_ID", "")
    monkeypatch.setenv("STRIPE_PRO_PRICE_ID", "")
    monkeypatch.setenv("STRIPE_PRO_YEARLY_PRICE_ID", "")
    # An empty Price ID input must NOT classify as "basic"
    plan, cycle = derive_plan_from_price("")
    assert plan == "pro"  # falls through to the default
    assert cycle == "monthly"
