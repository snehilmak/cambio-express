"""Web-push notification delivery.

Operators provision a VAPID keypair once + set three env vars
(see `docs/push-keys.md`); when they're not set, `is_enabled()`
returns False and every endpoint that calls into push is a no-op.

  - `is_enabled()` — predicate guarding the opt-in UI + every
    delivery attempt.
  - `vapid_public_key()` — frontend reads this through the
    `/api/push/public-key` route to build a `PushManager`
    subscription. Returns "" when push isn't configured so the
    JSON envelope can advertise `null` to the client.
  - `send_push(db, user_id, title, body, url, tag)` — fan out
    one notification to every device the user has subscribed.
    Returns the number of successful sends. Dead subscriptions
    (404 / 410 from the push provider) are cleaned up so we
    don't keep retrying ghosts.

The push payload is a JSON dict with `title` / `body` / `url` /
`tag` keys. None values are dropped — the service-worker uses
the presence of `tag` to decide whether to coalesce
notifications.

VAPID keys are read at import time from the environment. Tests
that monkeypatch the env need to monkeypatch the module-level
constants too (or use `setattr` on the module).
"""
import json
import logging
import os

from sqlalchemy.orm import Session


logger = logging.getLogger(__name__)


VAPID_PUBLIC_KEY  = os.environ.get("VAPID_PUBLIC_KEY", "")
VAPID_PRIVATE_KEY = os.environ.get("VAPID_PRIVATE_KEY", "")
VAPID_SUBJECT     = os.environ.get(
    "VAPID_SUBJECT", "mailto:admin@example.com",
)


def is_enabled() -> bool:
    """True iff both VAPID keys are configured. Without both, every
    delivery path no-ops + the frontend opt-in UI hides itself."""
    return bool(VAPID_PUBLIC_KEY and VAPID_PRIVATE_KEY)


def vapid_public_key() -> str:
    """The pub key the frontend uses to build a PushManager
    subscription. Empty string when push isn't configured."""
    return VAPID_PUBLIC_KEY


def send_push(
    db: Session,
    user_id: int,
    title: str,
    body: str = "",
    url: str = "/",
    tag: str | None = None,
) -> int:
    """Deliver a push notification to every device this user has
    subscribed. Returns the number of successful sends.

    Dead subscriptions (404 / 410 from the push provider, meaning
    the browser has revoked the subscription) are deleted so the
    next send doesn't retry them.

    No-ops + returns 0 when:
      - VAPID keys aren't configured (push disabled)
      - `pywebpush` isn't installed (optional dependency)

    Caller doesn't need to commit — this function commits its
    own cleanup deletes.
    """
    if not is_enabled():
        return 0
    try:
        from pywebpush import webpush, WebPushException
    except ImportError:
        logger.warning("pywebpush not installed; skipping send_push")
        return 0

    from api.Modules.Announcements.Models import PushSubscription

    payload_dict = {
        "title": title,
        "body": body,
        "url": url,
        "tag": tag,
    }
    payload = json.dumps(
        {k: v for k, v in payload_dict.items() if v is not None}
    )

    subs = (
        db.query(PushSubscription)
          .filter_by(user_id=user_id)
          .all()
    )
    sent = 0
    for s in subs:
        try:
            webpush(
                subscription_info={
                    "endpoint": s.endpoint,
                    "keys": {"p256dh": s.p256dh, "auth": s.auth},
                },
                data=payload,
                vapid_private_key=VAPID_PRIVATE_KEY,
                vapid_claims={"sub": VAPID_SUBJECT},
            )
            sent += 1
        except WebPushException as e:
            status = getattr(
                getattr(e, "response", None), "status_code", None,
            )
            if status in (404, 410):
                # Subscription gone — drop it.
                db.delete(s)
            else:
                logger.warning("push send failed (%s): %s", status, e)
    db.commit()
    return sent
