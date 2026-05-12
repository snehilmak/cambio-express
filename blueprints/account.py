"""Account / settings SPA-cutover redirects + small mutations.

Extracted from ``app.py`` as part of the D2 Blueprint split. Four
small 301 redirects (Settings, Profile, the legacy admin Security
tab, the referral-codes page) plus three small mutating endpoints
(theme toggle, notification-preferences redirect, single-passkey
delete) that pair well with the read-side surfaces.

  GET /account/security             301 → /app/settings
  GET /account/profile              301 → /app/account/profile
  GET /admin/settings/security      301 → /account/security (legacy
                                          tab URL kept alive for
                                          old bookmarks)
  GET /account/referrals            301 → /app/account/referrals
                                          (admin_required — only
                                          admins earn referral
                                          credits)
  GET /account/notifications        301 → /app/account/notifications
  POST /account/theme               persist user.theme_preference
                                    ("dark" / "light")
  POST /account/passkeys/<id>/delete delete one Passkey row owned
                                     by the current user

The WebAuthn passkey enrollment finishers
(/account/passkeys/register/{begin,finish}) and the WebAuthn login
finisher (/login/passkey/{begin,finish}) stay in app.py for now —
they touch session state and the WebAuthn challenge IDs that need
a careful move.

Endpoint-name churn:
  url_for("account_security")               → url_for("account.account_security")
  url_for("account_profile")                → url_for("account.account_profile")
  url_for("admin_settings_security_redirect") → url_for("account.admin_settings_security_redirect")
  url_for("admin_referrals")                → url_for("account.admin_referrals")
  url_for("account_notifications")          → url_for("account.account_notifications")
  url_for("account_theme")                  → url_for("account.account_theme")
  url_for("passkey_delete")                 → url_for("account.passkey_delete")

`account.account_theme` stays in `_TRIAL_EXEMPT` so a trial-
expired user can still toggle the dark/light theme without being
bounced to /subscribe.
"""
from __future__ import annotations

from flask import (
    Blueprint, flash, redirect, request, url_for,
)


bp = Blueprint("account", __name__)


@bp.route("/account/security", methods=["GET", "POST"])
def account_security():
    """301 → /app/settings. Password change + passkey list/delete
    were already on the SPA Settings page; passkey enrollment moved
    there too (FastAPI register/begin+finish bridge the WebAuthn
    challenge via a signed JWT since we can't share Flask's
    session). The legacy POST handlers
    /account/passkeys/register/begin+finish stay alive for
    in-flight Jinja requests mid-rollout."""
    from app import login_required
    return login_required(lambda: redirect("/app/settings", code=301))()


@bp.route("/account/profile", methods=["GET", "POST"])
def account_profile():
    """301 → /app/account/profile. Personal profile editor moved
    to React. Validation + persistence now live behind
    GET/PUT /api/v2/auth/profile."""
    from app import login_required
    return login_required(
        lambda: redirect("/app/account/profile", code=301)
    )()


@bp.route("/admin/settings/security", methods=["GET"])
def admin_settings_security_redirect():
    """Permanent redirect from the old admin-only Security tab to
    the new shared page. Keeps any bookmarks / external docs
    working."""
    from app import login_required
    return login_required(
        lambda: redirect(url_for("account.account_security"), code=301)
    )()


@bp.route("/account/referrals")
def admin_referrals():
    """301 → /app/account/referrals. Self-service code + stats
    moved to React. The lazy-mint-on-first-paid-visit and the
    trial-blocked behavior live behind /api/v2/admin/referrals
    now (returns 409 for trial admins; the SPA renders an
    upsell card pointing at /app/subscribe). Stub keeps
    url_for(...) working for the topbar crown + bounces old
    bookmarks."""
    from app import admin_required

    @admin_required
    def _h():
        return redirect("/app/account/referrals", code=301)

    return _h()


@bp.route("/account/notifications", methods=["GET", "POST"])
def account_notifications():
    """301 → /app/account/notifications. Toggle UI moved to React;
    GET/PUT /api/v2/auth/notifications drives persistence. The
    trial-toggle gating logic (admin/owner of a trialing store)
    moved into the api.Modules.Auth.Services.notifications module
    so SPA + Flask see the same `applies` state."""
    from app import login_required
    return login_required(
        lambda: redirect("/app/account/notifications", code=301)
    )()


@bp.route("/account/theme", methods=["POST"])
def account_theme():
    """Persist the user's UI theme preference.

    Lives as its own endpoint (not folded into /account/profile) so
    the toggle can be a one-click action with its own redirect
    target — submitting it from any page returns the user to where
    they were. Validates strictly: anything other than "dark" /
    "light" is treated as a no-op rather than wiping the column."""
    from app import current_user, db, login_required

    @login_required
    def _h():
        user = current_user()
        choice = (request.form.get("theme") or "").strip().lower()
        if choice in ("dark", "light"):
            user.theme_preference = choice
            db.session.commit()
            flash(f"Switched to {choice} mode.", "success")
        else:
            flash("Invalid theme — no change.", "error")
        # Bounce back to the referring page so the toggle works
        # from anywhere.
        nxt = (
            request.form.get("next")
            or request.referrer
            or url_for("account.account_profile")
        )
        return redirect(nxt)

    return _h()


@bp.route("/account/passkeys/<int:pk_id>/delete", methods=["POST"])
def passkey_delete(pk_id: int):
    """Delete one Passkey row owned by the current user."""
    from app import Passkey, current_user, db, login_required

    @login_required
    def _h():
        user = current_user()
        pk = Passkey.query.filter_by(
            id=pk_id, user_id=user.id,
        ).first_or_404()
        db.session.delete(pk)
        db.session.commit()
        flash("Passkey removed.", "success")
        return redirect(url_for("account.account_security"))

    return _h()
