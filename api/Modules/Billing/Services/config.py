"""Stripe environment-config helpers.

Three small predicates / accessors that read the Stripe env vars
without touching the Stripe SDK. Used by:

  - the FC connect modal (publishable key for Stripe.js)
  - the FC connect endpoint (configuration gate)
  - the superadmin Overview tab (mode badge)
  - the referral-credit Service (transactional gate)
  - any future Service that needs to know whether Stripe is wired
    up before issuing a SDK call

Pure reads — no SDK calls, no DB. Cheap to call on every request.

Also exports `init_stripe()` — the one place that assigns
`stripe.api_key` from the `STRIPE_SECRET_KEY` env var.  Called
from `create_app()` during boot.  Without this, every Stripe
SDK call ("No API key provided") fails — the Flask era had
`stripe.api_key = ...` at module top of `app.py` but the
FastAPI cutover dropped it; pilot users hit it on the Manage-
on-Stripe button because the portal endpoint has no other Stripe
dependency that would have flushed it out earlier.
"""
import logging
import os

import stripe


_log = logging.getLogger(__name__)


def init_stripe() -> None:
    """Initialize the global Stripe SDK key from the environment.

    Idempotent: safe to call multiple times (tests, lifespan
    restarts).  No-ops when `STRIPE_SECRET_KEY` is unset so dev /
    CI runs that don't configure Stripe still boot — the per-call
    `stripe_is_configured()` gate stops actual Stripe traffic.

    Should be invoked once per process during boot, before any
    Stripe SDK call.
    """
    sk = os.environ.get("STRIPE_SECRET_KEY", "")
    if not sk:
        _log.warning(
            "init_stripe: STRIPE_SECRET_KEY not set; Stripe SDK "
            "calls will fail with 'No API key provided' until "
            "the env var is configured.",
        )
        return
    stripe.api_key = sk


def stripe_is_configured() -> bool:
    """True iff `STRIPE_SECRET_KEY` is present in the environment.

    The cheapest gate before issuing any Stripe SDK call. Most
    routes that touch Stripe short-circuit on this so dev / CI
    runs don't hit the live API by accident.
    """
    return bool(os.environ.get("STRIPE_SECRET_KEY"))


def stripe_publishable_key() -> str:
    """The `pk_test_/pk_live_` key the browser uses to load Stripe.js.

    Required for the FC connect modal — `Stripe.js` can't
    initialize without it. Returns an empty string when unset
    so callers can treat absence as "Stripe not wired up".
    """
    return os.environ.get("STRIPE_PUBLISHABLE_KEY", "")


def stripe_mode() -> str:
    """`"live"` when `STRIPE_SECRET_KEY` starts with `sk_live_`,
    `"test"` otherwise (including for unset secrets that start
    with `sk_test_`). Empty string when no key is set.

    Used by the superadmin Overview tab to render the test/live
    mode badge — the same logic the health-check Service uses
    internally.
    """
    sk = os.environ.get("STRIPE_SECRET_KEY", "")
    if not sk:
        return ""
    return "live" if sk.startswith("sk_live_") else "test"
