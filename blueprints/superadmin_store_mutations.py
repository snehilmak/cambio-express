"""Superadmin per-store mutation handlers.

Extracted from ``app.py`` as part of the D2 Blueprint split. Six
POST handlers superadmin uses to flip a single store's billing /
addon state from the Controls UI (the Stores tab):

  POST /superadmin/stores/<int:store_id>/extend-trial
      Push the trial/grace deadlines forward by N days
      (default 7, max 180).
  POST /superadmin/stores/<int:store_id>/comp-plan
      Grant a free plan (basic|pro) bypassing Stripe — for
      friends/family/comps.
  POST /superadmin/stores/<int:store_id>/toggle-active
      Enable/disable the store account without touching billing.
  POST /superadmin/stores/<int:store_id>/extend-retention
      Push the 180-day data-retention deadline out by N days
      (default 30, max 720).
  POST /superadmin/stores/<int:store_id>/revert-to-trial
      Drop a paid/comped store back onto the 7-day trial. Keeps
      all data.
  POST /superadmin/stores/<int:store_id>/addons/<addon_key>/toggle
      Override switch for a store's add-ons. Bypasses the
      "needs paid plan" gate that admin_subscription_toggle_addon
      enforces.

Every mutation is audit-logged (``record_audit(...)``) and
redirects back to ``superadmin_redirects.superadmin_controls``
with ``?tab=stores`` so the operator lands on the same panel
they started from.

Helpers stay in app.py and are pulled in via late imports:
  ``_store_or_404``, ``_parse_extend_days``,
  ``_extended_deadline``, ``record_audit``,
  ``ADDONS_CATALOG``, ``db``, ``superadmin_required``,
  ``Store``.

Endpoint-name churn:
  url_for("superadmin_extend_trial")
    → url_for("superadmin_store_mutations.superadmin_extend_trial")
  ... (same shape for all 6)
"""
from __future__ import annotations

from datetime import datetime, timedelta

from flask import Blueprint, flash, redirect, request, url_for


bp = Blueprint("superadmin_store_mutations", __name__)


@bp.route(
    "/superadmin/stores/<int:store_id>/extend-trial", methods=["POST"],
)
def superadmin_extend_trial(store_id: int):
    """Push the store's trial/grace deadlines forward by N days
    (default 7)."""
    from app import (
        _extended_deadline, _parse_extend_days, _store_or_404,
        db, record_audit, superadmin_required,
    )

    @superadmin_required
    def _h():
        store = _store_or_404(store_id)
        days = _parse_extend_days(request.form, default=7, maximum=180)
        store.trial_ends_at = _extended_deadline(
            store.trial_ends_at, days,
        )
        store.grace_ends_at = store.trial_ends_at + timedelta(days=4)
        if store.plan == "inactive":
            store.plan = "trial"
            store.data_retention_until = None
            store.canceled_at = None
        record_audit(
            "extend_trial",
            target_type="store", target_id=store.id,
            details=f"+{days}d → {store.trial_ends_at.isoformat()}",
        )
        db.session.commit()
        flash(f"{store.name}: trial extended by {days} days.", "success")
        return redirect(url_for(
            "superadmin_redirects.superadmin_controls", tab="stores",
        ))

    return _h()


@bp.route(
    "/superadmin/stores/<int:store_id>/comp-plan", methods=["POST"],
)
def superadmin_comp_plan(store_id: int):
    """Grant a free plan (basic or pro) bypassing Stripe — for
    friends/family/comps."""
    from app import (
        _store_or_404, db, record_audit, superadmin_required,
    )

    @superadmin_required
    def _h():
        store = _store_or_404(store_id)
        plan = request.form.get("plan", "pro")
        if plan not in ("basic", "pro"):
            flash("Invalid plan.", "error")
            return redirect(url_for(
                "superadmin_redirects.superadmin_controls", tab="stores",
            ))
        store.plan = plan
        store.canceled_at = None
        store.data_retention_until = None
        record_audit(
            "comp_plan",
            target_type="store", target_id=store.id,
            details=f"granted {plan} (no Stripe)",
        )
        db.session.commit()
        flash(f"{store.name}: comped to {plan.title()}.", "success")
        return redirect(url_for(
            "superadmin_redirects.superadmin_controls", tab="stores",
        ))

    return _h()


@bp.route(
    "/superadmin/stores/<int:store_id>/toggle-active", methods=["POST"],
)
def superadmin_toggle_active(store_id: int):
    """Enable/disable the store account without touching billing
    state."""
    from app import (
        _store_or_404, db, record_audit, superadmin_required,
    )

    @superadmin_required
    def _h():
        store = _store_or_404(store_id)
        store.is_active = not store.is_active
        record_audit(
            "toggle_active",
            target_type="store", target_id=store.id,
            details=f"is_active={store.is_active}",
        )
        db.session.commit()
        flash(
            f"{store.name}: "
            f"{'active' if store.is_active else 'disabled'}.",
            "success",
        )
        return redirect(url_for(
            "superadmin_redirects.superadmin_controls", tab="stores",
        ))

    return _h()


@bp.route(
    "/superadmin/stores/<int:store_id>/extend-retention",
    methods=["POST"],
)
def superadmin_extend_retention(store_id: int):
    """Push the 180-day data-retention deadline out by N days
    (default 30)."""
    from app import (
        _extended_deadline, _parse_extend_days, _store_or_404,
        db, record_audit, superadmin_required,
    )

    @superadmin_required
    def _h():
        store = _store_or_404(store_id)
        days = _parse_extend_days(request.form, default=30, maximum=720)
        store.data_retention_until = _extended_deadline(
            store.data_retention_until, days,
        )
        record_audit(
            "extend_retention",
            target_type="store", target_id=store.id,
            details=(
                f"+{days}d → {store.data_retention_until.isoformat()}"
            ),
        )
        db.session.commit()
        flash(
            f"{store.name}: retention extended by {days} days.",
            "success",
        )
        return redirect(url_for(
            "superadmin_redirects.superadmin_controls", tab="stores",
        ))

    return _h()


@bp.route(
    "/superadmin/stores/<int:store_id>/revert-to-trial",
    methods=["POST"],
)
def superadmin_revert_to_trial(store_id: int):
    """Drop a paid/comped store back onto the 7-day trial. Keeps
    all data."""
    from app import (
        _store_or_404, db, record_audit, superadmin_required,
    )

    @superadmin_required
    def _h():
        store = _store_or_404(store_id)
        now = datetime.utcnow()
        store.plan = "trial"
        store.trial_ends_at = now + timedelta(days=7)
        store.grace_ends_at = now + timedelta(days=11)
        store.canceled_at = None
        store.data_retention_until = None
        record_audit(
            "revert_to_trial",
            target_type="store", target_id=store.id,
        )
        db.session.commit()
        flash(f"{store.name}: reverted to 7-day trial.", "success")
        return redirect(url_for(
            "superadmin_redirects.superadmin_controls", tab="stores",
        ))

    return _h()


@bp.route(
    "/superadmin/stores/<int:store_id>/addons/<addon_key>/toggle",
    methods=["POST"],
)
def superadmin_toggle_addon(store_id: int, addon_key: str):
    """Override switch for a store's add-ons. Bypasses the
    "needs paid plan" gate that admin_subscription_toggle_addon
    enforces — sometimes superadmin needs to flip an addon on for
    a pilot/comped store, or off for a non-paying one. Audit-
    logged so the override path is always attributable."""
    from app import (
        ADDONS_CATALOG, _store_or_404, db, record_audit,
        superadmin_required,
    )

    @superadmin_required
    def _h():
        store = _store_or_404(store_id)
        addon = ADDONS_CATALOG.get(addon_key)
        if not addon:
            flash("Unknown add-on.", "error")
            return redirect(url_for(
                "superadmin_redirects.superadmin_controls", tab="stores",
            ))
        keys = {
            k.strip() for k in (store.addons or "").split(",")
            if k.strip()
        }
        if addon_key in keys:
            keys.discard(addon_key)
            action = "remove_addon"
            msg = f"{store.name}: {addon['name']} turned off."
        else:
            keys.add(addon_key)
            action = "add_addon"
            msg = f"{store.name}: {addon['name']} activated."
        store.addons = ",".join(sorted(keys))
        record_audit(
            action,
            target_type="store", target_id=store.id,
            details=addon_key,
        )
        db.session.commit()
        flash(msg, "success")
        return redirect(url_for(
            "superadmin_redirects.superadmin_controls", tab="stores",
        ))

    return _h()
