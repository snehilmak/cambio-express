"""Subscribe flow — Stripe Checkout entry points.

Extracted from ``app.py`` as part of the D2 Blueprint split. Three
routes wrap the Stripe Checkout Session mint flow:

  GET  /subscribe            301 → /app/subscribe (plan picker)
  POST /subscribe/checkout   create a Stripe Checkout Session and
                              303-redirect to it (form action on
                              the plan-picker page)
  GET  /subscribe/success    301 → /app/subscribe/success (Stripe's
                              success_url lands here; SPA polls
                              /api/v2/admin/store-info every 2s
                              for ~30s to flip from "Payment
                              received" to "You're on Basic/Pro"
                              without a manual refresh)

The Stripe legwork lives in
``api.Modules.Billing.Services.create_checkout_session``; this
handler only adapts the Flask form / flash / redirect surface.

Sibling subscription-management routes (/admin/subscription/*) live
in ``blueprints/subscription.py`` — they're the "manage existing
plan" UI, while these are the "buy a new plan" UI.

Endpoint-name churn from this move:
  url_for("subscribe")          → url_for("billing.subscribe")
  url_for("subscribe_checkout") → url_for("billing.subscribe_checkout")
  url_for("subscribe_success")  → url_for("billing.subscribe_success")
"""
from __future__ import annotations

from flask import Blueprint, flash, redirect, request, url_for


bp = Blueprint("billing", __name__)


@bp.route("/subscribe")
def subscribe():
    """301 → /app/subscribe. SPA reads /api/v2/admin/store-info for
    the current plan and POSTs to /api/v2/billing/checkout to mint
    a Stripe Checkout Session."""
    from app import login_required
    return login_required(lambda: redirect("/app/subscribe", code=301))()


@bp.route("/subscribe/checkout", methods=["POST"])
def subscribe_checkout():
    """Create a Stripe Checkout Session for the chosen plan and
    redirect. Plan validation + Stripe Session creation delegate to
    ``api.Modules.Billing.Services.create_checkout_session``; this
    route handles the form parsing + flash/redirect glue.

    The webhook (``checkout.session.completed``) is what actually
    flips the store onto the new plan — this route only initiates
    the payment flow."""
    from app import app as flask_app, current_store, login_required
    from api.Modules.Billing.Services import (
        InvalidPlanError, StripeServiceError, create_checkout_session,
    )

    @login_required
    def _h():
        store = current_store()
        plan = request.form.get("plan", "").strip()
        try:
            url = create_checkout_session(
                store, plan=plan,
                success_url=url_for(
                    "billing.subscribe_success", _external=True,
                ),
                cancel_url=url_for("billing.subscribe", _external=True),
            )
        except InvalidPlanError:
            flash("Invalid plan selected.", "error")
            return redirect(url_for("billing.subscribe"))
        except StripeServiceError as e:
            flask_app.logger.error(f"Stripe error: {e.__cause__}")
            flash("Payment service error. Please try again.", "error")
            return redirect(url_for("billing.subscribe"))
        return redirect(url, code=303)

    return _h()


@bp.route("/subscribe/success")
def subscribe_success():
    """301 → /app/subscribe/success. Stripe Checkout's success_url
    points at this URL — the redirect chain (Stripe → here → /app)
    is opaque to the user. The SPA polls
    /api/v2/admin/store-info every 2s for ~30s so the page flips
    from "Payment received" to "You're on Basic/Pro" without a
    manual refresh."""
    from app import login_required
    return login_required(
        lambda: redirect("/app/subscribe/success", code=301)
    )()
