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
