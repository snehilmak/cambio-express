"""Public-facing landing + privacy redirects.

Extracted from ``app.py`` as part of the D2 Blueprint split. Two
trivial routes that 301 to the React SPA — both are public, no
auth, no app.py model dependencies beyond `Store` (used by the
PWA-cookie bounce path).

  GET /          PWA-aware bounce. If `ds_last_store` cookie names
                 an active store, redirect to /app/login/<slug>
                 (otherwise to /app/). Lets installed-PWA employees
                 reach their store's branded login when they tap the
                 home-screen icon, which always points at /.
  GET /privacy   301 → /app/privacy. Stripe Financial Connections
                 + Checkout link to this URL so the redirect is the
                 long-term home for the public privacy policy.

The cookie helpers (`_active_store_from_cookie`,
`_set_last_store_slug_cookie`, `LAST_STORE_SLUG_COOKIE`) stay in
app.py because the legacy /login routes still write the cookie.
This blueprint reads them via late import.
"""
from __future__ import annotations

from flask import Blueprint, redirect


bp = Blueprint("landing", __name__)


@bp.route("/")
def landing():
    """301 → /app/. The React SPA owns the marketing landing
    (frontend/src/routes/Landing.tsx) and the dashboard bounce.

    PWA preservation: when an installed-PWA employee opens their
    shortcut (which points at `/`), we honor the `ds_last_store`
    cookie and bounce straight to /app/login/<slug> so they land
    on their store's sign-in page rather than the marketing pitch.
    Without this an employee on a chromeless PWA install would
    have no way to type the URL back to their store. Cookie's set
    in /app/login/<slug> after a successful per-store sign-in, so
    only returning employees hit this branch."""
    from app import _active_store_from_cookie

    store = _active_store_from_cookie()
    if store:
        return redirect(f"/app/login/{store.slug}", code=302)
    return redirect("/app/", code=301)


@bp.route("/privacy")
def privacy():
    """301 to the React /app/privacy page. The legacy Jinja
    template is gone — the SPA owns the public privacy policy now.
    This stub keeps url_for('landing.privacy') working in
    still-Jinja templates and bounces old bookmarks (plus the
    Stripe-side privacy URL on Financial Connections + Checkout,
    which both link here)."""
    return redirect("/app/privacy", code=301)
