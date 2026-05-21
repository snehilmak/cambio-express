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


class StripeNotConfiguredError(Exception):
    """Raised when a Stripe SDK call site detects the global
    ``stripe.api_key`` is empty.  Distinct from
    ``StripeServiceError`` (which wraps SDK failures) so the
    Controller can surface a clear "Stripe isn't configured —
    admin action needed" message instead of the generic "Payment
    service error" that pilot users were hitting.
    """


def _is_prod_environment() -> bool:
    """``True`` when ``APP_BASE_URL`` points at HTTPS — same
    predicate used elsewhere as the prod gate.  Missing
    Stripe config in prod escalates from WARNING to CRITICAL so
    the operator notices in Sentry + Render alerts."""
    return os.environ.get("APP_BASE_URL", "").startswith("https://")


def init_stripe() -> None:
    """Initialize the global Stripe SDK key from the environment +
    run a health probe so a missing / invalid / mode-mismatched
    key is caught at boot, not on the first user-facing request.

    Idempotent: safe to call multiple times (tests, lifespan
    restarts).

    Behaviour:
      * ``STRIPE_SECRET_KEY`` unset:
          - prod (``APP_BASE_URL`` starts with ``https://``):
            CRITICAL log — every billing route will 502 until
            the env var is set, operator needs to fix.
          - dev / CI: WARNING — the per-call
            ``stripe_is_configured()`` gate stops actual Stripe
            traffic so the app still boots.

      * ``STRIPE_SECRET_KEY`` set:
          - assign to ``stripe.api_key``
          - call ``stripe.Account.retrieve()`` (probe).  Account
            retrieves don't count against rate limits + cost
            nothing.
          - on success: INFO with account id + mode
          - ``stripe.error.AuthenticationError``: CRITICAL —
            the key is set but Stripe rejected it (revoked,
            typo, wrong env).  Service-layer ``StripeNotConfigured``
            still raises on each call so users see the friendly
            message.
          - any other ``StripeError``: WARN (could be transient
            network).  We don't escalate transient hiccups.

      * Mode-mismatch check (separate from probe): if
        ``STRIPE_PUBLISHABLE_KEY`` is set and its mode disagrees
        with the secret key (one ``sk_live_*`` + one
        ``pk_test_*``), CRITICAL log.  Mismatches make Stripe.js
        fail silently in the browser.
    """
    sk = os.environ.get("STRIPE_SECRET_KEY", "")
    if not sk:
        if _is_prod_environment():
            _log.critical(
                "init_stripe: STRIPE_SECRET_KEY not set in production. "
                "Every billing route will 502 with 'No API key "
                "provided' until the env var is configured on Render. "
                "Action: set STRIPE_SECRET_KEY in the Render dashboard "
                "(starts with sk_live_ for production).",
            )
        else:
            _log.warning(
                "init_stripe: STRIPE_SECRET_KEY not set; Stripe SDK "
                "calls will fail with 'No API key provided' until "
                "the env var is configured.",
            )
        return

    stripe.api_key = sk

    # Boot-time health probe — catches mis-configured / revoked /
    # mode-wrong keys at startup instead of waiting for a user to
    # click Manage-on-Stripe.
    try:
        acct = stripe.Account.retrieve()
        mode = "live" if sk.startswith("sk_live_") else "test"
        _log.info(
            "init_stripe: Stripe SDK reachable; account=%s mode=%s",
            acct.get("id", "?") if hasattr(acct, "get") else "?", mode,
        )
    except stripe.error.AuthenticationError as exc:  # type: ignore[attr-defined]
        _log.critical(
            "init_stripe: STRIPE_SECRET_KEY is set but Stripe rejected "
            "it (`AuthenticationError`).  Most likely cause: the key "
            "was revoked in the Stripe Dashboard, or a typo.  "
            "Detail: %s", exc,
        )
    except stripe.error.StripeError as exc:  # type: ignore[attr-defined]
        _log.warning(
            "init_stripe: Stripe probe failed (likely transient): %s",
            exc,
        )

    # Publishable / secret key mode-pairing check.
    pk = os.environ.get("STRIPE_PUBLISHABLE_KEY", "")
    if pk:
        sk_mode = "live" if sk.startswith("sk_live_") else "test"
        pk_mode = "live" if pk.startswith("pk_live_") else "test"
        if sk_mode != pk_mode:
            _log.critical(
                "init_stripe: STRIPE_SECRET_KEY is %s but "
                "STRIPE_PUBLISHABLE_KEY is %s.  Stripe.js will "
                "fail silently in the browser ('No such session') "
                "with mismatched keys.  Action: align both keys to "
                "the same mode in the Render dashboard.",
                sk_mode, pk_mode,
            )


def require_stripe_configured() -> None:
    """Raise ``StripeNotConfiguredError`` when the global SDK key
    is empty.  Service-layer call sites use this as a cheap gate
    BEFORE the SDK call so the user-facing error message clearly
    says "Stripe isn't configured" rather than the generic
    "Payment service error".

    Cheap: no DB hit, no SDK call.  Safe to put at the top of
    every Stripe-touching Service function.
    """
    if not stripe.api_key:
        raise StripeNotConfiguredError(
            "Stripe API key is not set; the operator must configure "
            "STRIPE_SECRET_KEY before billing flows will work.",
        )


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
