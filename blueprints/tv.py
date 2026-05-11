"""TV display routes — simple slice.

Extracted from ``app.py`` as part of the D2 Blueprint split. This
first slice covers the two simplest routes; the heavier ones
(/api/tv-pair/init, /api/tv-pair/status, /tv-display/countries/<id>,
/tv/<token>, /tv/device/<device_token>) stay in app.py for now —
they depend on TV-specific helpers (_generate_pair_code,
_generate_device_token, _render_tv_board) that need to move together
in a follow-up PR.

  GET /tv-display              redirect → /app/tv-display
                                (login_required; SPA serves the
                                 actual admin UI)
  GET /tv/logo/<type>/<slug>   stream a catalog logo BLOB with
                                year-long Cache-Control + a
                                MIME-type whitelist

Late imports keep this Blueprint independent of app.py at module-
load time — same pattern as the push and owner blueprints.
"""
from __future__ import annotations

from flask import Blueprint, abort, make_response, redirect


bp = Blueprint("tv", __name__)


# MIME types accepted on upload AND served back. Anything not in
# this set returns a 404 — keeps a corrupted DB row from spitting
# arbitrary bytes at a browser.
_LOGO_ALLOWED_MIMES = {
    "image/png", "image/jpeg", "image/webp", "image/svg+xml",
}


@bp.route("/tv-display")
def admin_tv_display():
    """301 → /app/tv-display. The admin landing moved to React; the
    SPA reads from /api/v2/tv-display/overview and POSTs to the JSON
    write endpoints under that prefix. Stub keeps
    url_for('tv.admin_tv_display') working in still-Jinja chrome
    (the sidebar nav link) and bounces old bookmarks. The addon-not-
    active error renders inside the SPA from the 409 the overview
    endpoint returns — no server-side gate here."""
    from app import login_required
    return login_required(lambda: redirect("/app/tv-display", code=301))()


@bp.route("/tv/logo/<catalog_type>/<slug>")
def tv_catalog_logo(catalog_type: str, slug: str):
    """Stream the BLOB for a catalog logo. Year-long Cache-Control;
    cache-bust by ?v=<timestamp> on the embedding template.

    Public, no auth — the TV display itself is public-by-token, and
    the logos shown on it can't reasonably be auth-gated. Brute-force
    enumeration is not a concern (logos are intentionally displayed
    on-screen for customers in the shop). We DO want aggressive
    browser caching so the rate board doesn't re-fetch every logo on
    every 30s refresh; templates append ?v=<updated_at_unix> to bust
    the cache when an admin re-uploads."""
    from app import TVCatalogLogo

    if catalog_type not in ("company", "bank"):
        abort(404)
    row = TVCatalogLogo.query.filter_by(
        catalog_type=catalog_type, slug=slug,
    ).first()
    if not row or row.mime_type not in _LOGO_ALLOWED_MIMES:
        abort(404)
    resp = make_response(row.blob)
    resp.headers["Content-Type"] = row.mime_type
    resp.headers["Content-Length"] = str(len(row.blob))
    # Year-long immutable cache. Templates append ?v=<unix> so a
    # re-upload changes the URL → fresh fetch on next render.
    resp.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    # Block image-format sniffing — the served bytes match the
    # whitelisted mime exactly.
    resp.headers["X-Content-Type-Options"] = "nosniff"
    return resp
