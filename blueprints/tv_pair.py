"""Fire TV / Google TV pair-code JSON API.

Two public JSON endpoints driving the device-initiated pairing flow:

  POST /api/tv-pair/init    Mint a fresh 6-char pair code + a stable
                            device_token. The Fire TV app displays
                            the code and starts polling /status.
  GET  /api/tv-pair/status  Poll endpoint. Returns:
                              200 {status: "pending", code,
                                   ttl_seconds}   — waiting for op
                              200 {status: "claimed", display_url,
                                   ...}            — operator bound
                                                     the code; app
                                                     loads the URL
                              200 {status: "expired"} — code timed
                                                         out or pair
                                                         was revoked

Always returns 200 so the Fire TV can branch off the JSON. Unknown
tokens get treated as "expired" so a fresh /init is the recovery
path — stronger UX guarantee than 404'ing the whole poll loop.

No auth — anyone with the Fire TV app can request a code; the
addon gate sits on /tv-display/claim where the admin binds the
code to a paying store.

Uses plain SQLAlchemy via ``SessionLocal()`` so the Final-phase
Flask-SQLAlchemy retirement doesn't have to revisit these.
"""
from __future__ import annotations

from datetime import datetime

from flask import Blueprint, jsonify, request, url_for

from api.Core.Database import SessionLocal


bp = Blueprint("tv_pair", __name__)


@bp.route("/api/tv-pair/init", methods=["POST"])
def tv_pair_init():
    """The Fire TV app calls this on launch. Creates a
    TVPendingPair with a fresh code + device_token and returns
    both."""
    from api.Modules.TVDisplay.Models import TVPendingPair
    from app import _PAIR_CODE_LIFETIME, _generate_device_token, _generate_pair_code

    payload = request.get_json(silent=True) or {}
    device_label = (payload.get("device_label") or "").strip()[:80]
    now = datetime.utcnow()

    with SessionLocal() as s:
        # Loop on code collision (rare with a 387M space, free to retry).
        code = None
        for _ in range(8):
            code = _generate_pair_code()
            if not s.query(TVPendingPair).filter_by(code=code).first():
                break

        pending = TVPendingPair(
            code=code,
            device_token=_generate_device_token(),
            device_label=device_label,
            created_at=now,
            expires_at=now + _PAIR_CODE_LIFETIME,
        )
        s.add(pending)
        s.commit()
        body = {
            "code":         pending.code,
            "device_token": pending.device_token,
            "expires_at":   pending.expires_at.isoformat() + "Z",
            "ttl_seconds":  int(_PAIR_CODE_LIFETIME.total_seconds()),
        }
    return jsonify(body)


@bp.route("/api/tv-pair/status", methods=["GET"])
def tv_pair_status():
    """The Fire TV polls this with its device_token. Always 200 so
    the Fire TV can branch off the JSON. Unknown tokens get treated
    as "expired" so a fresh /init is the recovery path."""
    from api.Modules.TVDisplay.Models import TVDisplay, TVPairing, TVPendingPair
    from api.Modules.Tenancy.Models import Store
    from app import store_has_addon

    token = (request.args.get("token") or "").strip()
    if not token:
        return jsonify({"status": "expired"}), 200

    with SessionLocal() as s:
        # Already claimed?
        pairing = (
            s.query(TVPairing)
             .filter_by(device_token=token, revoked_at=None)
             .first()
        )
        if pairing is not None:
            display = s.get(TVDisplay, pairing.display_id)
            store = s.get(Store, display.store_id) if display else None
            if display and store and store_has_addon(store, "tv_display"):
                display_url = url_for(
                    "tv_board.tv_device_display",
                    device_token=token,
                    _external=True,
                )
                title = display.title or "Money Transfer Rates"
                store_name = store.name
                return jsonify({
                    "status":      "claimed",
                    "display_url": display_url,
                    "store_name":  store_name,
                    "title":       title,
                }), 200
            # Pairing exists but addon is gone — same as expired.
            return jsonify({"status": "expired"}), 200

        pending = (
            s.query(TVPendingPair).filter_by(device_token=token).first()
        )
        if not pending:
            return jsonify({"status": "expired"}), 200
        if pending.expires_at < datetime.utcnow():
            return jsonify({"status": "expired"}), 200
        if pending.claimed_at is not None:
            # Pending row was claimed but the resulting TVPairing was
            # already revoked, or the addon was yanked. Re-init.
            return jsonify({"status": "expired"}), 200
        # Still pending. Return the code so the Fire TV can re-display
        # it after a process death / config change without losing the
        # bound code.
        ttl = int((pending.expires_at - datetime.utcnow()).total_seconds())
        return jsonify({
            "status":      "pending",
            "code":        pending.code,
            "ttl_seconds": max(0, ttl),
        }), 200
