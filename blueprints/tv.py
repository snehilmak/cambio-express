"""TV display routes — public logo serving.

Public, no auth: the TV display itself is public-by-token, and the
logos shown on it can't reasonably be auth-gated. Aggressive
browser caching so the rate board doesn't re-fetch logos on every
30s refresh; cache-bust by ``?v=<unix>`` on the embedding template.

The admin landing (``/tv-display`` GET) is handled by the
``spa_cutover`` redirect hook — no Flask handler needed.
"""
from __future__ import annotations

from flask import Blueprint, abort, make_response

from api.Core.Database import SessionLocal


bp = Blueprint("tv", __name__)


# MIME types accepted on upload AND served back. Anything not in
# this set returns a 404 — keeps a corrupted DB row from spitting
# arbitrary bytes at a browser.
_LOGO_ALLOWED_MIMES = {
    "image/png", "image/jpeg", "image/webp", "image/svg+xml",
}


@bp.route("/tv/logo/<catalog_type>/<slug>")
def tv_catalog_logo(catalog_type: str, slug: str):
    """Stream the BLOB for a catalog logo. Year-long Cache-Control;
    cache-bust by ``?v=<unix>`` on the embedding template."""
    if catalog_type not in ("company", "bank"):
        abort(404)
    from app import TVCatalogLogo
    with SessionLocal() as s:
        row = (
            s.query(TVCatalogLogo)
             .filter_by(catalog_type=catalog_type, slug=slug)
             .first()
        )
        if not row or row.mime_type not in _LOGO_ALLOWED_MIMES:
            abort(404)
        # Capture the bytes + mime before the session closes — the
        # ORM row is detached once we exit the `with` block.
        blob = row.blob
        mime = row.mime_type
    resp = make_response(blob)
    resp.headers["Content-Type"] = mime
    resp.headers["Content-Length"] = str(len(blob))
    # Year-long immutable cache. Templates append ?v=<unix> so a
    # re-upload changes the URL → fresh fetch on next render.
    resp.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    # Block image-format sniffing — the served bytes match the
    # whitelisted mime exactly.
    resp.headers["X-Content-Type-Options"] = "nosniff"
    return resp
