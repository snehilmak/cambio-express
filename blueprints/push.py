"""Web Push subscription + delivery routes.

Extracted from ``app.py`` as part of the D2 Blueprint split. The
canonical implementation already lives in
``api.Modules.Notifications.Services.push`` — these are the four
HTTP endpoints that wrap it for the SPA:

  GET  /api/push/public-key    return the VAPID key (or null when push
                               is disabled — keeps deployments without
                               VAPID configured from spamming the
                               console with red 501s)
  POST /api/push/subscribe     persist a PushSubscription for the
                               current user + device
  POST /api/push/unsubscribe   delete a PushSubscription by endpoint
  POST /api/push/test          fire a test notification to the caller's
                               own devices

The PushSubscription model + current_user() helper still live in
app.py; the route handlers use late imports rather than a register-
with-deps pattern so the Blueprint stays a self-contained module.
Late imports are evaluated once at first request, then cached.
"""
from flask import Blueprint, jsonify, request


bp = Blueprint("push", __name__)


# Late imports inside every route — the Notifications service module
# transitively imports api.Modules.Billing.Models which does
# `from app import FeatureFlag`. Importing it at module load time
# from this Blueprint creates a circular dependency because
# `app.py` is still finishing its own init when it imports us.
# Once both modules have finished loading, late imports succeed
# instantly (cached in sys.modules).


@bp.route("/api/push/public-key")
def push_public_key():
    """Return the VAPID public key so the SPA can build a
    PushManager subscription. Returns ``key: null`` when VAPID
    isn't configured so the opt-in button self-hides instead of
    spamming console errors."""
    from api.Modules.Notifications.Services import push as push_svc
    from api.Modules.Notifications.Services import push_is_enabled
    return jsonify({
        "key": push_svc.VAPID_PUBLIC_KEY if push_is_enabled() else None,
    })


@bp.route("/api/push/subscribe", methods=["POST"])
def push_subscribe():
    from app import PushSubscription, current_user, db
    from api.Modules.Notifications.Services import push_is_enabled

    u = current_user()
    if not u:
        return jsonify({"error": "auth"}), 401
    if not push_is_enabled():
        return jsonify({"error": "push not configured"}), 501
    data = request.get_json(silent=True) or {}
    endpoint = (data.get("endpoint") or "").strip()
    keys = data.get("keys") or {}
    p256dh = (keys.get("p256dh") or "").strip()
    auth = (keys.get("auth") or "").strip()
    if not endpoint or not p256dh or not auth:
        return jsonify({"error": "missing fields"}), 400
    existing = PushSubscription.query.filter_by(
        user_id=u.id, endpoint=endpoint,
    ).first()
    if not existing:
        db.session.add(PushSubscription(
            user_id=u.id, endpoint=endpoint, p256dh=p256dh, auth=auth,
            user_agent=(request.headers.get("User-Agent") or "")[:255],
        ))
        db.session.commit()
    return jsonify({"ok": True})


@bp.route("/api/push/unsubscribe", methods=["POST"])
def push_unsubscribe():
    from app import PushSubscription, current_user, db

    u = current_user()
    if not u:
        return jsonify({"error": "auth"}), 401
    endpoint = (request.get_json(silent=True) or {}).get("endpoint", "")
    if endpoint:
        PushSubscription.query.filter_by(
            user_id=u.id, endpoint=endpoint,
        ).delete()
        db.session.commit()
    return jsonify({"ok": True})


@bp.route("/api/push/test", methods=["POST"])
def push_test():
    """Fire a test push to the caller's own devices."""
    from app import current_user, db
    from api.Modules.Notifications.Services import send_push

    u = current_user()
    if not u:
        return jsonify({"error": "auth"}), 401
    n = send_push(
        db.session, u.id, "DineroBook",
        "Push notifications are working on this device.", url="/",
    )
    return jsonify({"sent": n})
