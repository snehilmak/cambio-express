"""Superadmin discount / feature-flag / announcement mutations.

Extracted from ``app.py`` as part of the D2 Blueprint split. Eight
POST handlers that mutate platform-wide state from the
Controls UI tabs:

  Discounts (2 routes)
    POST /superadmin/discounts/new
    POST /superadmin/discounts/<int:dc_id>/toggle

  Feature flags (3 routes)
    POST /superadmin/features/new
    POST /superadmin/features/<string:key>/toggle-global
    POST /superadmin/features/<string:key>/stores/<int:store_id>

  Announcements (3 routes)
    POST /superadmin/announcements/new
    POST /superadmin/announcements/<int:ann_id>/toggle
    POST /superadmin/announcements/<int:ann_id>/delete

Every mutation is audit-logged via ``record_audit(...)`` and
redirects back to
``superadmin_redirects.superadmin_controls?tab=<…>`` so the
operator lands on the same panel they started from.

Helpers stay in app.py (pulled in via late imports):
  ``record_audit``, ``current_user``, ``db``,
  ``_store_or_404``, ``_sync_discount_to_stripe``,
  ``broadcast_announcement``, ``superadmin_required``,
  ``DiscountCode``, ``FeatureFlag``, ``StoreFeatureOverride``,
  ``Announcement``, ``stripe`` (module).

No url_for callers — these POSTs are submitted from the Controls
UI directly to literal paths; endpoint-name namespacing is silent.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta

from flask import (
    Blueprint, abort, flash, redirect, request, url_for,
)


bp = Blueprint("superadmin_misc_mutations", __name__)


# ── Discounts ────────────────────────────────────────────────────


@bp.route("/superadmin/discounts/new", methods=["POST"])
def superadmin_new_discount():
    """Create a discount code; sync to Stripe if the key is
    configured."""
    from app import (
        DiscountCode, _sync_discount_to_stripe, current_user, db,
        record_audit, stripe, superadmin_required,
    )

    @superadmin_required
    def _h():
        code = request.form.get("code", "").strip().upper()
        if not code or not re.match(r"^[A-Z0-9_-]{3,40}$", code):
            flash("Code must be 3–40 chars (A-Z, 0-9, _, -).", "error")
            return redirect(url_for(
                "superadmin_redirects.superadmin_controls",
                tab="discounts",
            ))
        if DiscountCode.query.filter_by(code=code).first():
            flash("That code already exists.", "error")
            return redirect(url_for(
                "superadmin_redirects.superadmin_controls",
                tab="discounts",
            ))
        kind = request.form.get("kind", "percent")
        percent = int(request.form.get("percent_off") or 0) if kind == "percent" else 0
        amount_cents = (
            int(float(request.form.get("amount_off") or 0) * 100)
            if kind == "amount" else 0
        )
        if kind == "percent" and not (1 <= percent <= 100):
            flash("Percent off must be 1–100.", "error")
            return redirect(url_for(
                "superadmin_redirects.superadmin_controls",
                tab="discounts",
            ))
        if kind == "amount" and amount_cents <= 0:
            flash("Amount off must be greater than zero.", "error")
            return redirect(url_for(
                "superadmin_redirects.superadmin_controls",
                tab="discounts",
            ))
        duration = request.form.get("duration", "once")
        duration_months = (
            int(request.form.get("duration_months") or 0)
            if duration == "repeating" else None
        )
        max_redemptions = int(request.form.get("max_redemptions") or 0) or None
        expires_days = int(request.form.get("expires_days") or 0)
        expires_at = (
            datetime.utcnow() + timedelta(days=expires_days)
            if expires_days else None
        )

        dc = DiscountCode(
            code=code,
            label=request.form.get("label", "").strip(),
            percent_off=percent or None,
            amount_off_cents=amount_cents or None,
            duration=duration,
            duration_in_months=duration_months,
            max_redemptions=max_redemptions,
            expires_at=expires_at,
            created_by=current_user().id,
        )
        db.session.add(dc)
        db.session.flush()
        if stripe.api_key:
            _sync_discount_to_stripe(dc)
        record_audit(
            "create_discount",
            target_type="discount", target_id=dc.id,
            details=f"{dc.code} {dc.value_label}",
        )
        db.session.commit()
        flash(f"Discount code {code} created.", "success")
        return redirect(url_for(
            "superadmin_redirects.superadmin_controls", tab="discounts",
        ))

    return _h()


@bp.route("/superadmin/discounts/<int:dc_id>/toggle", methods=["POST"])
def superadmin_toggle_discount(dc_id: int):
    """Activate/deactivate a discount code locally and in Stripe."""
    from app import (
        DiscountCode, app as flask_app, db, record_audit, stripe,
        superadmin_required,
    )

    @superadmin_required
    def _h():
        dc = db.session.get(DiscountCode, dc_id) or abort(404)
        dc.is_active = not dc.is_active
        if dc.stripe_promotion_code_id:
            try:
                stripe.PromotionCode.modify(
                    dc.stripe_promotion_code_id, active=dc.is_active,
                )
            except Exception as e:
                flask_app.logger.warning(f"Stripe promo toggle failed: {e}")
        record_audit(
            "toggle_discount",
            target_type="discount", target_id=dc.id,
            details=f"active={dc.is_active}",
        )
        db.session.commit()
        flash(
            f"{dc.code}: "
            f"{'active' if dc.is_active else 'disabled'}.",
            "success",
        )
        return redirect(url_for(
            "superadmin_redirects.superadmin_controls", tab="discounts",
        ))

    return _h()


# ── Feature flags ────────────────────────────────────────────────


@bp.route("/superadmin/features/new", methods=["POST"])
def superadmin_new_feature():
    """Declare a new feature flag. Key must be a short lowercase
    identifier."""
    from app import (
        FeatureFlag, db, record_audit, superadmin_required,
    )

    @superadmin_required
    def _h():
        key = request.form.get("key", "").strip().lower()
        if not re.match(r"^[a-z][a-z0-9_]{1,40}$", key):
            flash(
                "Flag key must be lowercase letters/numbers/underscore, "
                "2–41 chars.",
                "error",
            )
            return redirect(url_for(
                "superadmin_redirects.superadmin_controls", tab="features",
            ))
        if FeatureFlag.query.filter_by(key=key).first():
            flash("That flag already exists.", "error")
            return redirect(url_for(
                "superadmin_redirects.superadmin_controls", tab="features",
            ))
        flag = FeatureFlag(
            key=key,
            label=request.form.get("label", "").strip() or key,
            description=request.form.get("description", "").strip(),
            enabled_by_default=request.form.get("enabled_by_default") == "on",
        )
        db.session.add(flag)
        record_audit(
            "create_feature", target_type="feature", target_id=key,
        )
        db.session.commit()
        flash(f"Feature flag {key} created.", "success")
        return redirect(url_for(
            "superadmin_redirects.superadmin_controls", tab="features",
        ))

    return _h()


@bp.route(
    "/superadmin/features/<string:key>/toggle-global", methods=["POST"],
)
def superadmin_toggle_feature_global(key: str):
    """Flip a feature's global default on/off."""
    from app import (
        FeatureFlag, db, record_audit, superadmin_required,
    )

    @superadmin_required
    def _h():
        flag = FeatureFlag.query.filter_by(key=key).first_or_404()
        flag.enabled_by_default = not flag.enabled_by_default
        record_audit(
            "toggle_feature_global",
            target_type="feature", target_id=flag.key,
            details=f"enabled_by_default={flag.enabled_by_default}",
        )
        db.session.commit()
        flash(
            f"Flag {key} globally "
            f"{'on' if flag.enabled_by_default else 'off'}.",
            "success",
        )
        return redirect(url_for(
            "superadmin_redirects.superadmin_controls", tab="features",
        ))

    return _h()


@bp.route(
    "/superadmin/features/<string:key>/stores/<int:store_id>",
    methods=["POST"],
)
def superadmin_set_feature_override(key: str, store_id: int):
    """Set or clear a per-store override for a feature flag.

    Form values: action = 'on' | 'off' | 'clear'.
    """
    from app import (
        FeatureFlag, StoreFeatureOverride, _store_or_404, current_user,
        db, record_audit, superadmin_required,
    )

    @superadmin_required
    def _h():
        FeatureFlag.query.filter_by(key=key).first_or_404()
        _store_or_404(store_id)
        action = request.form.get("action", "on")
        existing = StoreFeatureOverride.query.filter_by(
            store_id=store_id, flag_key=key,
        ).first()
        if action == "clear":
            if existing:
                db.session.delete(existing)
        else:
            enabled = action == "on"
            if existing:
                existing.enabled = enabled
                existing.updated_at = datetime.utcnow()
                existing.updated_by = current_user().id
            else:
                db.session.add(StoreFeatureOverride(
                    store_id=store_id, flag_key=key,
                    enabled=enabled, updated_by=current_user().id,
                ))
        record_audit(
            "set_feature_override",
            target_type="feature", target_id=key,
            details=f"store={store_id} action={action}",
        )
        db.session.commit()
        flash("Override updated.", "success")
        return redirect(url_for(
            "superadmin_redirects.superadmin_controls", tab="features",
        ))

    return _h()


# ── Announcements ────────────────────────────────────────────────


@bp.route("/superadmin/announcements/new", methods=["POST"])
def superadmin_new_announcement():
    """Post a banner shown to every user on every page until it
    expires. Optionally also email the announcement to every
    opted-in user if the ``broadcast`` checkbox is ticked."""
    from app import (
        Announcement, app as flask_app, broadcast_announcement,
        current_user, db, record_audit, superadmin_required,
    )

    @superadmin_required
    def _h():
        message = request.form.get("message", "").strip()
        if not message:
            flash("Announcement message is required.", "error")
            return redirect(url_for(
                "superadmin_redirects.superadmin_controls",
                tab="announcements",
            ))
        level = request.form.get("level", "info")
        if level not in ("info", "warning", "error", "success"):
            level = "info"
        try:
            days = int(request.form.get("expires_days") or 0)
        except ValueError:
            days = 0
        expires_at = (
            datetime.utcnow() + timedelta(days=days) if days else None
        )
        broadcast = bool(request.form.get("broadcast"))
        a = Announcement(
            message=message[:2000], level=level,
            is_active=True, expires_at=expires_at,
            created_by=current_user().id,
            broadcast_requested=broadcast,
        )
        db.session.add(a)
        db.session.flush()
        record_audit(
            "create_announcement",
            target_type="announcement", target_id=a.id,
            details=(
                f"{level}: {message[:80]}"
                + (" [broadcast]" if broadcast else "")
            ),
        )
        db.session.commit()
        # Broadcast synchronously. At current scale (a few hundred
        # users) this is sub-second. If we ever grow past ~2k
        # opted-in users, convert to a queued job — the sender is
        # already idempotent.
        if broadcast:
            try:
                sent = broadcast_announcement(a.id)
                flash(
                    f"Announcement posted and emailed to {sent} user(s).",
                    "success",
                )
            except Exception as e:
                flask_app.logger.warning(
                    f"announcement broadcast failed: {e}",
                )
                flash(
                    "Announcement posted, but the broadcast email "
                    "failed. Check the Email service card for details.",
                    "warning",
                )
        else:
            flash("Announcement posted.", "success")
        return redirect(url_for(
            "superadmin_redirects.superadmin_controls",
            tab="announcements",
        ))

    return _h()


@bp.route(
    "/superadmin/announcements/<int:ann_id>/toggle", methods=["POST"],
)
def superadmin_toggle_announcement(ann_id: int):
    """Enable or disable a posted announcement without deleting
    it."""
    from app import (
        Announcement, db, record_audit, superadmin_required,
    )

    @superadmin_required
    def _h():
        a = db.session.get(Announcement, ann_id) or abort(404)
        a.is_active = not a.is_active
        record_audit(
            "toggle_announcement",
            target_type="announcement", target_id=a.id,
            details=f"active={a.is_active}",
        )
        db.session.commit()
        flash(
            f"Announcement "
            f"{'enabled' if a.is_active else 'disabled'}.",
            "success",
        )
        return redirect(url_for(
            "superadmin_redirects.superadmin_controls",
            tab="announcements",
        ))

    return _h()


@bp.route(
    "/superadmin/announcements/<int:ann_id>/delete", methods=["POST"],
)
def superadmin_delete_announcement(ann_id: int):
    """Permanently remove an announcement. Toggle first if you
    might want it back."""
    from app import (
        Announcement, db, record_audit, superadmin_required,
    )

    @superadmin_required
    def _h():
        a = db.session.get(Announcement, ann_id) or abort(404)
        record_audit(
            "delete_announcement",
            target_type="announcement", target_id=a.id,
        )
        db.session.delete(a)
        db.session.commit()
        flash("Announcement deleted.", "success")
        return redirect(url_for(
            "superadmin_redirects.superadmin_controls",
            tab="announcements",
        ))

    return _h()
