"""Unit tests for Billing.Services.health (PR 53).

The health probe hits the Stripe API, so we stub `stripe.Account`,
`stripe.Price`, and `stripe.financial_connections.Session` via
monkeypatch. Tests cover the structural shape of the result + each
failure-mode branch the superadmin Overview tab depends on.
"""
from unittest.mock import MagicMock

import pytest


def _set_stripe_env(monkeypatch, *,
                    secret="sk_test_dummy",
                    publishable="pk_test_dummy",
                    webhook="whsec_dummy",
                    basic="price_basic",
                    basic_yearly="price_basic_year",
                    pro="price_pro",
                    pro_yearly="price_pro_year"):
    """Set the Stripe env vars the health probe reads."""
    monkeypatch.setenv("STRIPE_SECRET_KEY", secret) if secret else \
        monkeypatch.delenv("STRIPE_SECRET_KEY", raising=False)
    monkeypatch.setenv("STRIPE_PUBLISHABLE_KEY", publishable) if publishable else \
        monkeypatch.delenv("STRIPE_PUBLISHABLE_KEY", raising=False)
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", webhook) if webhook else \
        monkeypatch.delenv("STRIPE_WEBHOOK_SECRET", raising=False)
    monkeypatch.setenv("STRIPE_BASIC_PRICE_ID", basic) if basic else \
        monkeypatch.delenv("STRIPE_BASIC_PRICE_ID", raising=False)
    monkeypatch.setenv("STRIPE_BASIC_YEARLY_PRICE_ID", basic_yearly) if basic_yearly else \
        monkeypatch.delenv("STRIPE_BASIC_YEARLY_PRICE_ID", raising=False)
    monkeypatch.setenv("STRIPE_PRO_PRICE_ID", pro) if pro else \
        monkeypatch.delenv("STRIPE_PRO_PRICE_ID", raising=False)
    monkeypatch.setenv("STRIPE_PRO_YEARLY_PRICE_ID", pro_yearly) if pro_yearly else \
        monkeypatch.delenv("STRIPE_PRO_YEARLY_PRICE_ID", raising=False)


def _stub_stripe(monkeypatch, *,
                 account=None, price=None, fc=None):
    """Stub the Stripe SDK calls. `account`, `price`, and `fc` are
    each either a return value (success) or an Exception instance
    (failure)."""
    import stripe
    if account is None:
        account = {"id": "acct_test", "email": "ops@test.io"}
    if price is None:
        price = MagicMock(id="price_resolved")
    if fc is None:
        # Default: simulate the expected "No such customer" success
        # branch.
        fc = stripe.error.InvalidRequestError(
            "No such customer 'cus_test_invalid'", param="customer",
        )

    def acct_retrieve(*args, **kwargs):
        if isinstance(account, Exception):
            raise account
        return account
    def price_retrieve(*args, **kwargs):
        if isinstance(price, Exception):
            raise price
        return price
    def fc_create(*args, **kwargs):
        if isinstance(fc, Exception):
            raise fc
        return fc

    monkeypatch.setattr(stripe.Account, "retrieve", acct_retrieve)
    monkeypatch.setattr(stripe.Price, "retrieve", price_retrieve)
    monkeypatch.setattr(
        stripe.financial_connections.Session, "create", fc_create,
    )


# ── env-presence shape ─────────────────────────────────────


def test_no_secret_key_returns_early(monkeypatch):
    """No STRIPE_SECRET_KEY → top-level error string + ok=False,
    no Stripe calls made."""
    from api.Modules.Billing.Services import check_stripe_integration
    _set_stripe_env(monkeypatch, secret="")
    result = check_stripe_integration()
    assert result["ok"] is False
    assert "STRIPE_SECRET_KEY is not configured" in result["error"]
    assert result["env"]["secret_key"] is False


def test_env_booleans_reflect_presence(monkeypatch):
    from api.Modules.Billing.Services import check_stripe_integration
    _set_stripe_env(monkeypatch)
    _stub_stripe(monkeypatch)
    result = check_stripe_integration()
    assert result["env"]["secret_key"] is True
    assert result["env"]["publishable_key"] is True
    assert result["env"]["webhook_secret"] is True
    assert result["env"]["basic_price_id"] is True
    assert result["env"]["basic_yearly_price_id"] is True
    assert result["env"]["pro_price_id"] is True
    assert result["env"]["pro_yearly_price_id"] is True


# ── Account.retrieve ───────────────────────────────────────


def test_account_retrieval_success(monkeypatch):
    from api.Modules.Billing.Services import check_stripe_integration
    _set_stripe_env(monkeypatch)
    _stub_stripe(monkeypatch, account={
        "id": "acct_42", "email": "ops@example.com",
    })
    result = check_stripe_integration()
    assert result["ok"] is True
    assert result["account_id"] == "acct_42"
    assert result["account_email"] == "ops@example.com"


def test_account_retrieval_failure_short_circuits(monkeypatch):
    """Account API failure populates the top-level error and bails
    before checking individual prices."""
    from api.Modules.Billing.Services import check_stripe_integration
    _set_stripe_env(monkeypatch)
    _stub_stripe(
        monkeypatch,
        account=RuntimeError("Stripe is down"),
    )
    result = check_stripe_integration()
    assert result["ok"] is False
    assert "RuntimeError" in result["error"]
    # price_ok is initialized to False; nothing flipped to True
    assert all(v is False for v in result["price_ok"].values())


def test_mode_test_vs_live_detected_from_secret(monkeypatch):
    from api.Modules.Billing.Services import check_stripe_integration
    _set_stripe_env(monkeypatch, secret="sk_live_real")
    _stub_stripe(monkeypatch)
    result = check_stripe_integration()
    assert result["mode"] == "live"

    _set_stripe_env(monkeypatch, secret="sk_test_dummy")
    _stub_stripe(monkeypatch)
    result = check_stripe_integration()
    assert result["mode"] == "test"


# ── Price.retrieve ─────────────────────────────────────────


def test_price_resolution_success_marks_ok(monkeypatch):
    from api.Modules.Billing.Services import check_stripe_integration
    _set_stripe_env(monkeypatch)
    _stub_stripe(monkeypatch)
    result = check_stripe_integration()
    assert result["price_ok"]["basic"] is True
    assert result["price_ok"]["basic_yearly"] is True
    assert result["price_ok"]["pro"] is True
    assert result["price_ok"]["pro_yearly"] is True
    assert all(v == "" for v in result["price_errors"].values())


def test_price_failure_recorded_in_errors(monkeypatch):
    """Price.retrieve failure populates the per-plan error string,
    truncated to 160 chars."""
    import stripe
    from api.Modules.Billing.Services import check_stripe_integration
    _set_stripe_env(monkeypatch)
    long_msg = "x" * 500
    _stub_stripe(
        monkeypatch,
        price=stripe.error.InvalidRequestError(long_msg, param="id"),
    )
    result = check_stripe_integration()
    # Every price plan failed → all 4 records the error.
    assert all(v is False for v in result["price_ok"].values())
    for v in result["price_errors"].values():
        assert v != ""
        assert len(v) <= 160


# ── key_pair_match ─────────────────────────────────────────


def test_key_pair_match_test_mode(monkeypatch):
    from api.Modules.Billing.Services import check_stripe_integration
    _set_stripe_env(
        monkeypatch, secret="sk_test_x", publishable="pk_test_x",
    )
    _stub_stripe(monkeypatch)
    result = check_stripe_integration()
    assert result["key_pair_match"] is True


def test_key_pair_mismatch_test_secret_with_live_pk(monkeypatch):
    from api.Modules.Billing.Services import check_stripe_integration
    _set_stripe_env(
        monkeypatch, secret="sk_test_x", publishable="pk_live_x",
    )
    _stub_stripe(monkeypatch)
    result = check_stripe_integration()
    assert result["key_pair_match"] is False


# ── Financial Connections probe ────────────────────────────


def test_fc_no_such_customer_is_success(monkeypatch):
    """The expected branch: FC.create rejects the fake customer ID
    with 'No such customer' / 'resource_missing'. That confirms FC
    is enabled and the secret key is valid."""
    import stripe
    from api.Modules.Billing.Services import check_stripe_integration
    _set_stripe_env(monkeypatch)
    _stub_stripe(
        monkeypatch,
        fc=stripe.error.InvalidRequestError(
            "No such customer 'cus_test_invalid'", param="customer",
        ),
    )
    result = check_stripe_integration()
    assert result["fc_ok"] is True
    assert result["fc_error"] == ""


def test_fc_real_invalid_request_recorded(monkeypatch):
    """A non-customer InvalidRequestError (e.g. permissions / missing
    feature) is a real problem — fc_ok stays False, error string is
    populated and truncated."""
    import stripe
    from api.Modules.Billing.Services import check_stripe_integration
    _set_stripe_env(monkeypatch)
    _stub_stripe(
        monkeypatch,
        fc=stripe.error.InvalidRequestError(
            "Feature not enabled on this account", param=None,
        ),
    )
    result = check_stripe_integration()
    assert result["fc_ok"] is False
    assert "Feature not enabled" in result["fc_error"]


def test_fc_unexpected_exception_recorded(monkeypatch):
    """Any non-Stripe exception is recorded with type prefix."""
    from api.Modules.Billing.Services import check_stripe_integration
    _set_stripe_env(monkeypatch)
    _stub_stripe(monkeypatch, fc=RuntimeError("network down"))
    result = check_stripe_integration()
    assert result["fc_ok"] is False
    assert "RuntimeError" in result["fc_error"]
    assert "network down" in result["fc_error"]


# ── legacy Flask wrapper ───────────────────────────────────


def test_legacy_app_helper_delegates(monkeypatch):
    """app.stripe_health_check now calls the Service."""
    from app import stripe_health_check as legacy
    _set_stripe_env(monkeypatch, secret="")
    result = legacy()
    assert result["ok"] is False
    assert "STRIPE_SECRET_KEY is not configured" in result["error"]
