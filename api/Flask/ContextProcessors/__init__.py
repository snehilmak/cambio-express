"""Flask context processors — values injected into every Jinja
template render. Registered onto the Flask app via
``register(app, db, current_user_fn, current_store_fn)``.

Surfaces:
  trial_status, trial_days_left, store, announcements,
  my_referral_code  — trial banner + crown
  is_impersonating, impersonated_store_name — impersonation banner
  active_addons     — sidebar feature-link gating
  theme             — dark/light token flip on <html data-theme=…>
"""
from __future__ import annotations

from datetime import datetime

from flask import session

from api.Modules.Announcements.Services import active_announcements
from api.Modules.Billing.Models import ReferralCode
from api.Modules.Billing.Services import (
    ensure_referral_code,
    get_trial_status,
    store_addon_keys,
)
from api.Modules.Tenancy.Models import Store


def register(app, db, current_user_fn, current_store_fn):
    """Wire every context processor onto the Flask `app`."""

    @app.context_processor
    def inject_trial_context():
        """trial_status, trial_days_left, store, announcements, my_referral_code."""
        try:
            announcements = active_announcements(db.session)
        except Exception:
            announcements = []
        user = current_user_fn()
        if not user:
            return {"trial_status": "exempt", "trial_days_left": 0, "store": None,
                    "announcements": announcements}
        if user.role in ("superadmin", "owner"):
            return {"trial_status": "exempt", "trial_days_left": 0, "store": None,
                    "announcements": announcements}
        store = current_store_fn()
        status = get_trial_status(store)
        days_left = 0
        if store and store.trial_ends_at:
            delta = store.trial_ends_at - datetime.utcnow()
            days_left = max(0, delta.days)
        my_referral_code = ""
        if (user.role == "admin"
            and store is not None
            and store.plan in ("basic", "pro")):
            try:
                rc = db.session.query(ReferralCode).filter_by(owner_store_id=store.id).first()
                if rc is None:
                    rc = ensure_referral_code(db.session, store)
                    db.session.commit()
                my_referral_code = rc.code if rc else ""
            except Exception as e:
                app.logger.warning(f"referral code lookup failed: {e}")
        return {"trial_status": status, "trial_days_left": days_left, "store": store,
                "announcements": announcements, "my_referral_code": my_referral_code}

    @app.context_processor
    def inject_impersonation_context():
        """is_impersonating + impersonated_store_name for the banner."""
        if "impersonator_user_id" not in session:
            return {"is_impersonating": False, "impersonated_store_name": ""}
        sid = session.get("store_id")
        store = db.session.get(Store, sid) if sid else None
        return {
            "is_impersonating": True,
            "impersonated_store_name": store.name if store else "(unknown store)",
        }

    @app.context_processor
    def inject_active_addons():
        """active_addons set for sidebar feature-link gating."""
        store = current_store_fn()
        return {"active_addons": store_addon_keys(store)}

    @app.context_processor
    def inject_theme():
        """Active UI theme: user preference or 'dark' default."""
        user = current_user_fn()
        if user is None:
            return {"theme": "dark"}
        pref = getattr(user, "theme_preference", None)
        if pref not in ("dark", "light"):
            return {"theme": "dark"}
        return {"theme": pref}
