"""Public-facing TV rate-board endpoints.

Two public-no-auth fullscreen rate-board views:

  GET /tv/<token>            Fullscreen rate board for the shared
                             ``TVDisplay.public_token``.
  GET /tv/device/<dt>        Per-device rate board bound to a single
                             ``TVPairing.device_token``. Bumps
                             ``TVPairing.last_seen_at`` on render.

Both delegate to ``_render_tv_board(display, store)`` in app.py.
The helper takes a session as its third arg so this blueprint can
stay off Flask-SQLAlchemy.
"""
from __future__ import annotations

from datetime import datetime

from flask import Blueprint, abort

from api.Core.Database import SessionLocal


bp = Blueprint("tv_board", __name__)


@bp.route("/tv/<token>")
def tv_public_display(token: str):
    """Fullscreen rate board, no auth. Anyone with the URL sees it."""
    from api.Modules.TVDisplay.Models import TVDisplay
    from api.Modules.Tenancy.Models import Store
    from app import _render_tv_board, store_has_addon
    with SessionLocal() as s:
        display = (
            s.query(TVDisplay).filter_by(public_token=token).first()
        )
        if display is None:
            abort(404)
        store = s.get(Store, display.store_id)
        if not store or not store_has_addon(store, "tv_display"):
            abort(404)
        return _render_tv_board(display, store, s)


@bp.route("/tv/device/<device_token>")
def tv_device_display(device_token: str):
    """Per-device rate-board URL handed to a Fire TV companion app
    after a successful pair-code redeem. Bumps
    ``TVPairing.last_seen_at`` on render."""
    from api.Modules.TVDisplay.Models import TVDisplay, TVPairing
    from api.Modules.Tenancy.Models import Store
    from app import _render_tv_board, store_has_addon
    with SessionLocal() as s:
        pairing = (
            s.query(TVPairing).filter_by(device_token=device_token).first()
        )
        if not pairing or pairing.revoked_at is not None:
            abort(404)
        display = s.get(TVDisplay, pairing.display_id)
        if not display:
            abort(404)
        store = s.get(Store, display.store_id)
        if not store or not store_has_addon(store, "tv_display"):
            abort(404)
        pairing.last_seen_at = datetime.utcnow()
        s.commit()
        return _render_tv_board(display, store, s)
