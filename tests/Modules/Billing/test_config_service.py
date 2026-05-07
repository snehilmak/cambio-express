"""Unit tests for Billing.Services.config (PR 54)."""


# ── stripe_is_configured ───────────────────────────────────


def test_is_configured_true_when_secret_set(monkeypatch):
    from api.Modules.Billing.Services import stripe_is_configured
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_x")
    assert stripe_is_configured() is True


def test_is_configured_false_when_secret_missing(monkeypatch):
    from api.Modules.Billing.Services import stripe_is_configured
    monkeypatch.delenv("STRIPE_SECRET_KEY", raising=False)
    assert stripe_is_configured() is False


def test_is_configured_false_when_secret_empty(monkeypatch):
    """Empty string is treated as 'not configured' — same as
    unset."""
    from api.Modules.Billing.Services import stripe_is_configured
    monkeypatch.setenv("STRIPE_SECRET_KEY", "")
    assert stripe_is_configured() is False


# ── stripe_publishable_key ─────────────────────────────────


def test_publishable_key_returns_env_value(monkeypatch):
    from api.Modules.Billing.Services import stripe_publishable_key
    monkeypatch.setenv("STRIPE_PUBLISHABLE_KEY", "pk_test_x")
    assert stripe_publishable_key() == "pk_test_x"


def test_publishable_key_returns_empty_when_unset(monkeypatch):
    """Unset → empty string (not None). Templates concat this into
    Stripe.js init attribute, so empty is a safe sentinel."""
    from api.Modules.Billing.Services import stripe_publishable_key
    monkeypatch.delenv("STRIPE_PUBLISHABLE_KEY", raising=False)
    assert stripe_publishable_key() == ""


# ── stripe_mode ────────────────────────────────────────────


def test_mode_live_when_secret_starts_with_sk_live(monkeypatch):
    from api.Modules.Billing.Services import stripe_mode
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_live_real")
    assert stripe_mode() == "live"


def test_mode_test_when_secret_starts_with_sk_test(monkeypatch):
    from api.Modules.Billing.Services import stripe_mode
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_dummy")
    assert stripe_mode() == "test"


def test_mode_empty_when_secret_unset(monkeypatch):
    from api.Modules.Billing.Services import stripe_mode
    monkeypatch.delenv("STRIPE_SECRET_KEY", raising=False)
    assert stripe_mode() == ""


def test_mode_test_for_unknown_prefix(monkeypatch):
    """Anything that isn't sk_live_ defaults to test (matches the
    legacy contract — defensively never returns 'live' unless we
    can prove it)."""
    from api.Modules.Billing.Services import stripe_mode
    monkeypatch.setenv("STRIPE_SECRET_KEY", "rk_anything_else")
    assert stripe_mode() == "test"


# ── legacy Flask wrappers ──────────────────────────────────


def test_legacy_app_helpers_delegate(monkeypatch):
    """All three legacy helpers in app.py now delegate to the
    Service. Smoke-test the round trip."""
    from app import (
        stripe_is_configured as legacy_is_configured,
        stripe_mode as legacy_mode,
        stripe_publishable_key as legacy_pk,
    )
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_live_x")
    monkeypatch.setenv("STRIPE_PUBLISHABLE_KEY", "pk_live_x")
    assert legacy_is_configured() is True
    assert legacy_mode() == "live"
    assert legacy_pk() == "pk_live_x"

    monkeypatch.delenv("STRIPE_SECRET_KEY", raising=False)
    monkeypatch.delenv("STRIPE_PUBLISHABLE_KEY", raising=False)
    assert legacy_is_configured() is False
    assert legacy_mode() == ""
    assert legacy_pk() == ""
