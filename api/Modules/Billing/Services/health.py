"""Stripe integration health-check.

Diagnostic probe used by the superadmin Overview tab. Returns a
single dict describing:
  - which Stripe env vars are present (booleans)
  - whether we can reach the Stripe Account API (i.e. the secret
    key is valid)
  - whether each configured price ID resolves
  - whether the secret/publishable key pair share a mode (test vs.
    live mismatch is the most common silent Stripe.js failure)
  - whether Financial Connections is reachable + enabled

Pure read — no mutations. Hits the Stripe API on each call so the
caller decides when to invoke (the legacy app gates on "Overview
tab is active" to keep the cost off other pages).
"""
import os

import stripe

from api.Modules.Billing.Services.checkout import resolve_price_ids
from typing import Any


def check_stripe_integration() -> dict[str, Any]:
    """Probe Stripe and return a structured health report.

    Shape (all keys always present so the template can render
    without conditional defensiveness):

        {
          "env": {
            "secret_key":            bool,
            "publishable_key":       bool,
            "webhook_secret":        bool,
            "basic_price_id":        bool,
            "basic_yearly_price_id": bool,
            "pro_price_id":          bool,
            "pro_yearly_price_id":   bool,
          },
          "ok":            bool,            # Account.retrieve OK
          "error":         str,             # populated on top-level failure
          "account_id":    str,             # filled on success
          "account_email": str,
          "mode":          "test" | "live",
          "price_ok":      {plan: bool},    # one per resolved price
          "price_errors":  {plan: str},     # truncated to 160 chars
          "fc_ok":         bool,            # Financial Connections reachable
          "fc_error":      str,             # truncated to 160 chars
          "key_pair_match": bool,           # pk_test_/sk_test_, pk_live_/sk_live_
        }
    """
    env = {
        "secret_key":      bool(os.environ.get("STRIPE_SECRET_KEY")),
        "publishable_key": bool(os.environ.get("STRIPE_PUBLISHABLE_KEY")),
        "webhook_secret":  bool(os.environ.get("STRIPE_WEBHOOK_SECRET")),
    }
    prices = resolve_price_ids()
    env["basic_price_id"]        = bool(prices["basic"])
    env["basic_yearly_price_id"] = bool(prices["basic_yearly"])
    env["pro_price_id"]          = bool(prices["pro"])
    env["pro_yearly_price_id"]   = bool(prices["pro_yearly"])
    result: dict[str, Any] = {
        "env": env,
        "ok": False,
        "error": "",
        "price_ok": {
            "basic": False, "basic_yearly": False,
            "pro": False, "pro_yearly": False,
        },
        # Per-price error string from the Stripe API. Lets the
        # superadmin overview show "No such price …" or "test/live
        # mismatch" without having to guess.
        "price_errors": {
            "basic": "", "basic_yearly": "",
            "pro": "", "pro_yearly": "",
        },
        "fc_ok": False,
        "fc_error": "",
        "key_pair_match": True,
    }
    if not env["secret_key"]:
        result["error"] = "STRIPE_SECRET_KEY is not configured."
        return result

    try:
        acct = stripe.Account.retrieve()
        result["ok"] = True
        result["account_id"] = acct.get("id", "")
        result["account_email"] = acct.get("email", "")
        # Test-mode keys start with sk_test_; live keys with sk_live_.
        secret = os.environ.get("STRIPE_SECRET_KEY", "")
        result["mode"] = "test" if secret.startswith("sk_test_") else "live"
    except Exception as e:
        result["error"] = f"{type(e).__name__}: {e}"
        return result

    for plan, pid in prices.items():
        if not pid:
            continue
        try:
            stripe.Price.retrieve(pid)
            result["price_ok"][plan] = True
        except Exception as e:
            # Capture the message so the superadmin overview can
            # show why the price didn't validate (most common: a
            # price made in live mode but the secret key is from
            # test mode, or vice versa). Truncated for the badge.
            result["price_errors"][plan] = str(e)[:160]

    # Publishable / secret key pairing: pk_test_ must go with
    # sk_test_ and pk_live_ with sk_live_. Mismatched keys make
    # Stripe.js fail silently in the browser ("No such session")
    # which is hard to diagnose without this hint.
    pk = os.environ.get("STRIPE_PUBLISHABLE_KEY", "")
    if pk:
        pk_mode = "live" if pk.startswith("pk_live_") else "test"
        result["key_pair_match"] = (pk_mode == result.get("mode", ""))

    # FC dry probe: try to create a Financial Connections session
    # for a fake customer. We don't expect it to succeed — we're
    # testing whether the API is reachable and FC is enabled on
    # this account.
    if env["secret_key"]:
        try:
            stripe.financial_connections.Session.create(
                account_holder={"type": "customer", "customer": "cus_test_invalid"},
                permissions=["balances"],
                filters={"countries": ["US"]},
            )
            result["fc_ok"] = True
        except stripe.error.InvalidRequestError as e:  # type: ignore[attr-defined]
            # "No such customer" / "resource_missing" is the
            # expected branch — FC is enabled, key is good, only
            # the placeholder customer was rejected. Anything
            # else is a real problem.
            msg = str(e)
            if "No such customer" in msg or "resource_missing" in msg:
                result["fc_ok"] = True
            else:
                result["fc_error"] = msg[:160]
        except Exception as e:
            result["fc_error"] = f"{type(e).__name__}: {e}"[:160]
    return result
