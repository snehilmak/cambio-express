"""Regression guard for `api.Modules.Billing.Services.config.init_stripe`.

The legacy Flask `app.py` had `stripe.api_key = os.environ.get(
'STRIPE_SECRET_KEY', '')` at module top so every Stripe SDK call
inherited the key.  The FastAPI cutover lost that line entirely
— the SDK silently returned "No API key provided" on every
billing_portal / checkout call until the env var was set with
the right OTHER name (`STRIPE_API_KEY` is the only name Stripe's
Python SDK auto-loads; we use `STRIPE_SECRET_KEY` by convention).

These tests pin the contract:

  1. `init_stripe()` writes `STRIPE_SECRET_KEY` into
     `stripe.api_key`.
  2. With no env var set, it logs a warning + leaves `api_key`
     alone (so dev / CI without Stripe still boot).
  3. `create_app()` (the FastAPI factory) calls it during boot.
"""
import os
from unittest.mock import patch

import stripe


def test_init_stripe_sets_api_key_from_env(monkeypatch):
    """`STRIPE_SECRET_KEY` in env → `stripe.api_key` after init."""
    from api.Modules.Billing.Services.config import init_stripe

    # Snapshot + restore so we don't leak the test key into
    # other test files in the same process.
    original = stripe.api_key
    try:
        monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_init_guard")
        # Clear so the assertion measures the effect of init_stripe.
        stripe.api_key = None  # type: ignore[assignment]
        init_stripe()
        assert stripe.api_key == "sk_test_init_guard"
    finally:
        stripe.api_key = original


def test_init_stripe_noops_without_env(monkeypatch, caplog):
    """No env var → no assignment, warning logged.  This is the
    dev / CI path; we don't want every test run hitting real
    Stripe."""
    from api.Modules.Billing.Services.config import init_stripe

    original = stripe.api_key
    try:
        monkeypatch.delenv("STRIPE_SECRET_KEY", raising=False)
        stripe.api_key = None  # type: ignore[assignment]
        with caplog.at_level("WARNING", logger=(
            "api.Modules.Billing.Services.config"
        )):
            init_stripe()
        assert stripe.api_key is None
        # WARNING line should reference the missing env var so a
        # operator grepping logs sees what to set.
        assert any(
            "STRIPE_SECRET_KEY" in rec.message for rec in caplog.records
        ), caplog.records
    finally:
        stripe.api_key = original


def test_create_app_initializes_stripe(monkeypatch):
    """`create_app()` must call `init_stripe()` so the global SDK
    key is populated before any route handler runs.  This is the
    actual regression guard for the "No API key provided" bug
    that hit pilot users on Manage-on-Stripe."""
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_create_app_guard")
    monkeypatch.setenv("DINEROBOOK_SKIP_INIT_DB", "1")
    original = stripe.api_key
    try:
        stripe.api_key = None  # type: ignore[assignment]
        from api.main import create_app
        create_app()
        assert stripe.api_key == "sk_test_create_app_guard"
    finally:
        stripe.api_key = original


# ── Boot-time health probe ─────────────────────────────────────


def test_init_stripe_logs_critical_on_auth_error(monkeypatch, caplog):
    """A valid-looking key that Stripe rejects (revoked, typo) is a
    CRITICAL log line — operator should see it in Sentry / Render
    alerts immediately, not on the first user-facing 502."""
    from api.Modules.Billing.Services.config import init_stripe

    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_live_rejected_by_stripe")
    original = stripe.api_key
    try:
        stripe.api_key = None  # type: ignore[assignment]
        # Patch Account.retrieve to simulate Stripe rejecting the key.
        def _raise_auth(*a, **kw):
            raise stripe.error.AuthenticationError("Invalid API Key provided")
        monkeypatch.setattr(stripe.Account, "retrieve", _raise_auth)
        with caplog.at_level(
            "CRITICAL", logger="api.Modules.Billing.Services.config",
        ):
            init_stripe()
        # The CRITICAL line is the operator's alert path — pin it.
        msgs = [r.message for r in caplog.records if r.levelname == "CRITICAL"]
        assert any("rejected" in m.lower() or "authenticationerror" in m.lower()
                   for m in msgs), msgs
    finally:
        stripe.api_key = original


def test_init_stripe_only_warns_on_transient_stripe_error(monkeypatch, caplog):
    """Non-auth StripeError at boot is most often a transient network
    blip — log WARN, don't escalate.  Real auth issues use
    AuthenticationError above."""
    from api.Modules.Billing.Services.config import init_stripe

    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_transient")
    original = stripe.api_key
    try:
        stripe.api_key = None  # type: ignore[assignment]
        def _raise_api(*a, **kw):
            raise stripe.error.APIConnectionError("Network down")
        monkeypatch.setattr(stripe.Account, "retrieve", _raise_api)
        with caplog.at_level("WARNING", logger=(
            "api.Modules.Billing.Services.config"
        )):
            init_stripe()
        crit = [r for r in caplog.records if r.levelname == "CRITICAL"]
        warns = [r for r in caplog.records if r.levelname == "WARNING"]
        assert not crit, "transient errors should not escalate"
        assert any("probe failed" in r.message.lower() for r in warns), warns
    finally:
        stripe.api_key = original


def test_init_stripe_escalates_missing_env_in_production(monkeypatch, caplog):
    """Missing env var in prod (APP_BASE_URL is HTTPS) escalates to
    CRITICAL.  Dev / CI stays at WARNING.  This is the "operator
    deployed without setting the env var" safety net."""
    from api.Modules.Billing.Services.config import init_stripe

    monkeypatch.delenv("STRIPE_SECRET_KEY", raising=False)
    monkeypatch.setenv("APP_BASE_URL", "https://dinerobook.com")
    original = stripe.api_key
    try:
        stripe.api_key = None  # type: ignore[assignment]
        with caplog.at_level("CRITICAL", logger=(
            "api.Modules.Billing.Services.config"
        )):
            init_stripe()
        crit = [r for r in caplog.records if r.levelname == "CRITICAL"]
        assert any("STRIPE_SECRET_KEY" in r.message for r in crit), crit
    finally:
        stripe.api_key = original


def test_init_stripe_flags_key_mode_mismatch(monkeypatch, caplog):
    """`sk_live_*` with `pk_test_*` (or vice versa) is a config
    bug — Stripe.js fails silently in the browser.  CRITICAL so
    the operator sees it before customers do."""
    from api.Modules.Billing.Services.config import init_stripe

    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_live_mode_mismatch_guard")
    monkeypatch.setenv("STRIPE_PUBLISHABLE_KEY", "pk_test_wrong_mode")
    original = stripe.api_key
    try:
        stripe.api_key = None  # type: ignore[assignment]
        # Account.retrieve must succeed so the mismatch check runs.
        class _FakeAccount(dict):
            def get(self, k, d=""): return "acct_test_xyz" if k == "id" else d
        monkeypatch.setattr(
            stripe.Account, "retrieve",
            lambda *a, **kw: _FakeAccount(),
        )
        with caplog.at_level("CRITICAL", logger=(
            "api.Modules.Billing.Services.config"
        )):
            init_stripe()
        crit = [r.message for r in caplog.records if r.levelname == "CRITICAL"]
        assert any("STRIPE_PUBLISHABLE_KEY" in m for m in crit), crit
    finally:
        stripe.api_key = original


# ── Service-layer guard ────────────────────────────────────────


def test_require_stripe_configured_raises_when_unset():
    """The Service-layer guard fires `StripeNotConfiguredError` when
    `stripe.api_key` is empty — distinct from `StripeServiceError`
    so the Controller can render a clearer user message."""
    from api.Modules.Billing.Services.config import (
        StripeNotConfiguredError, require_stripe_configured,
    )
    import pytest

    original = stripe.api_key
    try:
        stripe.api_key = ""  # type: ignore[assignment]
        with pytest.raises(StripeNotConfiguredError):
            require_stripe_configured()
    finally:
        stripe.api_key = original


def test_require_stripe_configured_passes_when_set():
    """No raise when the key is set — the guard is a cheap predicate,
    not an SDK call."""
    from api.Modules.Billing.Services.config import require_stripe_configured

    original = stripe.api_key
    try:
        stripe.api_key = "sk_test_guard_present"
        # Should not raise.
        require_stripe_configured()
    finally:
        stripe.api_key = original


# ── Controller-layer 503 path ──────────────────────────────────


def test_checkout_returns_503_when_stripe_not_configured(
    client, test_store_id, monkeypatch,
):
    """When `stripe.api_key` is empty, the checkout endpoint surfaces
    a clear "Billing isn't configured" 503 instead of the generic
    "Payment service error" 502.  Operator action is to set the
    env var, not retry."""
    from tests.Modules.Billing.test_billing_controllers import _login_admin

    original = stripe.api_key
    try:
        stripe.api_key = ""  # type: ignore[assignment]
        token = _login_admin(client, test_store_id)
        resp = client.post(
            "/api/v2/billing/checkout",
            json={"plan": "basic"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 503, resp.get_data(as_text=True)
        body = resp.get_json()
        assert "configur" in body["detail"].lower()
        assert "STRIPE_SECRET_KEY" in body["detail"]
    finally:
        stripe.api_key = original


def test_portal_returns_503_when_stripe_not_configured(
    client, test_store_id, monkeypatch,
):
    """Same 503 surface for the portal endpoint — distinguishes
    'Stripe isn't wired up' from 'Stripe call failed'."""
    from tests.Modules.Billing.test_billing_controllers import (
        _login_admin, _set_store_customer_id,
    )

    _set_store_customer_id(test_store_id, "cus_test_503")
    original = stripe.api_key
    try:
        stripe.api_key = ""  # type: ignore[assignment]
        token = _login_admin(client, test_store_id)
        resp = client.post(
            "/api/v2/billing/portal",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 503, resp.get_data(as_text=True)
        body = resp.get_json()
        assert "configur" in body["detail"].lower()
    finally:
        stripe.api_key = original
