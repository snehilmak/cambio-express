"""Stripe-backed subscription + add-on management routes.

Extracted from ``app.py`` as part of the D2 Blueprint split. Covers
the four routes under ``/admin/subscription/*``:

  GET  /admin/subscription                301 → /app/admin/subscription
                                            (SPA reads /api/v2/admin/
                                             subscription for plan +
                                             add-on state)
  POST /admin/subscription/billing-portal  open the Stripe billing
                                            portal in a new tab (303
                                            redirect to Stripe-issued
                                            URL)
  POST /admin/subscription/cancel          same as billing-portal but
                                            with a different flash on
                                            error — UX entry point
                                            after the retention-policy
                                            ack screen
  POST /admin/subscription/addons/<key>    toggle a feature add-on
                                            (CSV on Store.addons +
                                            optional landing redirect)

The Stripe legwork happens in
``api.Modules.Billing.Services.create_billing_portal_session``; these
handlers just adapt the Flask form / flash / redirect surface to it.

Endpoint-name churn from this move:
  url_for("admin_subscription")                 →  url_for("subscription.admin_subscription")
  url_for("admin_subscription_billing_portal")  →  url_for("subscription.admin_subscription_billing_portal")
  url_for("admin_subscription_cancel")          →  url_for("subscription.admin_subscription_cancel")
  url_for("admin_subscription_toggle_addon")    →  url_for("subscription.admin_subscription_toggle_addon")

Late imports inside route handlers keep this Blueprint independent
of ``app.py`` at module-load time — same pattern as the owner / tv
/ push blueprints.
"""
from __future__ import annotations

from flask import Blueprint, flash, redirect, url_for


bp = Blueprint("subscription", __name__)


def _open_billing_portal(store, error_msg: str, log_label: str = "billing portal"):
    """Flask-side adapter for the billing-portal Service. On success
    303-redirects to Stripe; on Stripe error flashes ``error_msg`` and
    redirects back to /admin/subscription.

    Caller handles the pre-checks (paid plan, stripe_customer_id
    present, etc.). Single source of truth lives in
    ``api.Modules.Billing.Services.create_billing_portal_session``."""
    from app import app as flask_app
    from api.Modules.Billing.Services import (
        StripeServiceError, create_billing_portal_session,
    )
    try:
        url = create_billing_portal_session(
            store,
            return_url=url_for(
                "subscription.admin_subscription", _external=True,
            ),
        )
        return redirect(url, code=303)
    except StripeServiceError as e:
        flask_app.logger.error(f"Stripe {log_label} error: {e.__cause__}")
        flash(error_msg, "error")
        return redirect(url_for("subscription.admin_subscription"))


@bp.route("/admin/subscription")
def admin_subscription():
    """301 → /app/admin/subscription. Subscription / add-ons page
    moved to React; the SPA reads /api/v2/admin/subscription for
    plan + add-on state. Stub keeps url_for(...) working in
    still-Jinja chrome and the legacy POST handlers below."""
    from app import admin_required

    @admin_required
    def _h():
        return redirect("/app/admin/subscription", code=301)

    return _h()


@bp.route("/admin/subscription/billing-portal", methods=["POST"])
def admin_subscription_billing_portal():
    """Open the Stripe billing portal so the operator can update
    cards, see invoices, etc. No-op if the store has no Stripe
    customer record yet."""
    from app import admin_required, current_store

    @admin_required
    def _h():
        store = current_store()
        if not store or not store.stripe_customer_id:
            flash(
                "No billing account found. Choose a plan to get started.",
                "error",
            )
            return redirect(url_for("subscribe"))
        return _open_billing_portal(
            store,
            error_msg="Could not open billing portal. Please try again.",
            log_label="billing portal",
        )

    return _h()


@bp.route("/admin/subscription/cancel", methods=["POST"])
def admin_subscription_cancel():
    """User has acknowledged the 6-month retention policy. Send them
    to the Stripe billing portal to actually cancel; the webhook will
    then mark the store inactive and start the 180-day retention
    timer."""
    from app import admin_required, current_store, store_has_paid_plan

    @admin_required
    def _h():
        store = current_store()
        if not store_has_paid_plan(store) or not store.stripe_customer_id:
            flash("No active subscription to cancel.", "error")
            return redirect(url_for("subscription.admin_subscription"))
        return _open_billing_portal(
            store,
            error_msg=(
                "Could not open the cancellation page. Please try again."
            ),
            log_label="billing portal (cancel)",
        )

    return _h()


@bp.route("/admin/subscription/addons/<addon_key>", methods=["POST"])
def admin_subscription_toggle_addon(addon_key: str):
    """Toggle a feature add-on on/off. Stripe billing for the
    subscription item is handled separately — this just flips the
    CSV on ``Store.addons`` so gated surfaces unlock immediately."""
    from app import (
        ADDONS_CATALOG, admin_required, current_store, db,
        store_addon_keys, store_has_paid_plan,
    )

    @admin_required
    def _h():
        store = current_store()
        addon = ADDONS_CATALOG.get(addon_key)
        if not addon:
            flash("Unknown add-on.", "error")
            return redirect(url_for("subscription.admin_subscription"))
        if not store_has_paid_plan(store):
            flash(
                "Add-ons require an active Basic or Pro subscription.",
                "error",
            )
            return redirect(url_for("subscription.admin_subscription"))
        if addon.get("status") == "coming_soon":
            flash(
                f"{addon['name']} is coming soon — we'll let you know "
                f"when it goes live.",
                "success",
            )
            return redirect(url_for("subscription.admin_subscription"))
        keys = store_addon_keys(store)
        if addon_key in keys:
            keys.discard(addon_key)
            flash(f"{addon['name']} turned off.", "success")
        else:
            keys.add(addon_key)
            flash(
                f"{addon['name']} is now active. Set up your display →",
                "success",
            )
        store.addons = ",".join(sorted(keys))
        db.session.commit()
        # When a feature has a dedicated dashboard, drop the user
        # there right after activating so they don't have to hunt
        # for it.
        if addon_key == "tv_display" and addon_key in keys:
            return redirect(url_for("tv.admin_tv_display"))
        return redirect(url_for("subscription.admin_subscription"))

    return _h()
