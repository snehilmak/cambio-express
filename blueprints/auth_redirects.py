"""Auth-side SPA-cutover redirects + logout.

Extracted from ``app.py`` as part of the D2 Blueprint split. Covers
the 5 routes around the SPA's signup / forgot-password / logout
flow:

  GET/POST /forgot-password         301 → /app/forgot-password
  GET/POST /reset-password/<token>  301 → /app/reset-password?token=…
  GET/POST /signup                  301 → /app/signup (or "Signups
                                            closed" template when
                                            SIGNUP_CLOSED is set)
  GET/POST /signup/owner            301 → /app/signup/owner (same
                                            SIGNUP_CLOSED gate)
  GET      /logout                  session.clear + redirect to the
                                     right login page (per-store
                                     login when an employee was
                                     signed in)

All five are thin shims; the heavy lifting lives in
``api.Modules.Auth.Controllers``. We keep these on the legacy URL
space because:

  - email links and old bookmarks still point at /reset-password/<…>
    + /forgot-password
  - the topbar avatar dropdown still uses ``url_for("logout")``
  - the marketing landing's "Get Started" CTA still hits /signup

Once every external pointer has migrated, these can retire. Until
then they're a true no-op cutover layer.

The login routes themselves (``/login``, ``/login/<slug>``,
``/login/2fa/*``, ``/login/passkey/*``) stay in ``app.py`` for now
— they share the session-setting / TOTP-pending state machine with
several other surfaces that haven't moved yet.

Endpoint-name churn from this move:
  url_for("forgot_password") → url_for("auth_redirects.forgot_password")
  url_for("reset_password")  → url_for("auth_redirects.reset_password")
  url_for("signup")          → url_for("auth_redirects.signup")
  url_for("signup_owner")    → url_for("auth_redirects.signup_owner")
  url_for("logout")          → url_for("auth_redirects.logout")
"""
from __future__ import annotations

from flask import (
    Blueprint, redirect, render_template, request, session, url_for,
)


bp = Blueprint("auth_redirects", __name__)


def _signup_closed() -> bool:
    """Read the gate at request time so Render env-var flips take
    effect without an app restart."""
    from app import SIGNUP_CLOSED
    return SIGNUP_CLOSED


@bp.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    """301 → /app/forgot-password. SPA submits to
    /api/v2/auth/forgot-password (handles SMTP delivery too)."""
    return redirect("/app/forgot-password", code=301)


@bp.route("/reset-password/<token>", methods=["GET", "POST"])
def reset_password(token: str):
    """301 → /app/reset-password?token=… The SPA reads the token
    from the query string so we hand it off there. Old reset
    emails in users' inboxes still point at this URL."""
    return redirect(f"/app/reset-password?token={token}", code=301)


@bp.route("/signup", methods=["GET", "POST"])
def signup():
    """301 → /app/signup when signups are open. With
    SIGNUP_CLOSED=1 render the invite-only notice directly so the
    user doesn't briefly see the SPA form before it 503s. Query
    string (?ref=, ?plan=) is preserved."""
    if _signup_closed():
        return render_template("signup_closed.html"), (
            200 if request.method == "GET" else 403
        )
    qs = request.query_string.decode("latin-1") if request.query_string else ""
    target = "/app/signup" + (f"?{qs}" if qs else "")
    return redirect(target, code=301)


@bp.route("/signup/owner", methods=["GET", "POST"])
def signup_owner():
    """301 → /app/signup/owner. Same SIGNUP_CLOSED gate as the
    regular signup route."""
    if _signup_closed():
        return render_template("signup_closed.html"), (
            200 if request.method == "GET" else 403
        )
    return redirect("/app/signup/owner", code=301)


@bp.route("/logout")
def logout():
    """Clear the Flask session. Employees go back to their store's
    branded login page (/login/<slug>); everyone else hits the
    generic /login."""
    from app import current_store, current_user

    user = current_user()
    store = current_store()
    is_employee = user and user.role == "employee"
    slug = store.slug if store else None
    session.clear()
    if is_employee and slug:
        return redirect(url_for("auth.login_store", slug=slug))
    return redirect(url_for("auth.login"))
