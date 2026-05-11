"""Account / settings SPA-cutover redirects.

Extracted from ``app.py`` as part of the D2 Blueprint split. Four
small 301 redirects pointing at the React Settings + Profile + the
referral-codes page:

  GET /account/security             301 → /app/settings (password +
                                            passkeys live there)
  GET /account/profile              301 → /app/account/profile
  GET /admin/settings/security      301 → /account/security (legacy
                                            tab URL kept alive for
                                            old bookmarks)
  GET /account/referrals            301 → /app/account/referrals
                                            (admin_required — only
                                            admins earn referral
                                            credits)

The mutating sibling routes (``/account/theme``, ``/account/
notifications``) and the WebAuthn passkey enrollment + login
finishers stay in app.py for now — they touch session state /
user mutations / WebAuthn challenge IDs that need a careful move.

Endpoint-name churn:
  url_for("account_security")
    → url_for("account.account_security")
  url_for("account_profile")
    → url_for("account.account_profile")
  url_for("admin_settings_security_redirect")
    → url_for("account.admin_settings_security_redirect")
  url_for("admin_referrals")
    → url_for("account.admin_referrals")
"""
from __future__ import annotations

from flask import Blueprint, redirect, url_for


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
