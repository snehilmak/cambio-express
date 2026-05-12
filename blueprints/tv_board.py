"""Public-facing TV rate-board endpoints.

Extracted from ``app.py`` as part of the D2 Blueprint split. Two
public-no-auth fullscreen rate-board views:

  GET /tv/<token>            Fullscreen rate board for the shared
                             ``TVDisplay.public_token``. No chrome
                             (no base.html), so it works on a
                             smart-TV browser / Chromecast / Fire
                             TV WebView with no extra UI.
  GET /tv/device/<dt>        Per-device rate board bound to a
                             single ``TVPairing.device_token`` (the
                             token a Fire TV gets after a
                             successful pair-code redeem). Same
                             content as /tv/<public_token>; bumps
                             ``TVPairing.last_seen_at`` on every
                             render so the admin UI can show "last
                             seen 2 min ago".

Both delegate to ``_render_tv_board(display, store)`` which lives
in app.py and pulls the catalog logos, mt_companies grid, payout
banks, and rate cells together. The helper has ~80 lines of joins
that haven't moved out of app.py yet — late import keeps this
blueprint independent.

No url_for callers (these are accessed via the public token in
the URL, not through any internal Flask routing).
"""
from __future__ import annotations

from datetime import datetime

from flask import Blueprint, abort


bp = Blueprint("tv_board", __name__)


@bp.route("/tv/<token>")
def tv_public_display(token: str):
    """Fullscreen rate board, no auth. Anyone with the URL sees it.

    Tablets / Chromecasts use this URL directly. Fire TV companion
    apps go through /tv/device/<device_token> instead so the shared
    public_token never leaves the browser/Chromecast world."""
    from app import (
        Store, TVDisplay, _render_tv_board, db, store_has_addon,
    )

    display = TVDisplay.query.filter_by(public_token=token).first_or_404()
    store = db.session.get(Store, display.store_id)
    # If the store later removes the addon, the URL stops working —
    # belt-and-suspenders, since regenerate_token is the supported path.
    if not store or not store_has_addon(store, "tv_display"):
        abort(404)
    return _render_tv_board(display, store)


@bp.route("/tv/device/<device_token>")
def tv_device_display(device_token: str):
    """Per-device rate-board URL handed to a Fire TV companion app
    after a successful pair-code redeem. Bumps
    ``TVPairing.last_seen_at`` on render.

    404s on unknown device_token / revoked TVPairing / addon
    switched off after pairing."""
    from app import (
        Store, TVDisplay, TVPairing, _render_tv_board, db,
        store_has_addon,
    )

    pairing = TVPairing.query.filter_by(device_token=device_token).first()
    if not pairing or pairing.revoked_at is not None:
        abort(404)
    display = db.session.get(TVDisplay, pairing.display_id)
    if not display:
        abort(404)
    store = db.session.get(Store, display.store_id)
    if not store or not store_has_addon(store, "tv_display"):
        abort(404)
    pairing.last_seen_at = datetime.utcnow()
    db.session.commit()
    return _render_tv_board(display, store)
