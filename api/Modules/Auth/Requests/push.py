"""Web-push subscription schemas.

The SPA calls ``PushManager.subscribe()`` in the service worker
to get a subscription envelope from the browser, then POSTs the
relevant fields here so the server can stash them for later
delivery via ``api/Modules/Notifications/Services/push.send_push``.
"""
from pydantic import BaseModel, ConfigDict, Field


class PushStatusResponse(BaseModel):
    """Status of the push channel for the current user.

    * ``enabled`` — VAPID keys are configured server-side, so the
      backend can actually deliver pushes (False when the operator
      hasn't set ``VAPID_PUBLIC_KEY`` / ``VAPID_PRIVATE_KEY`` env
      vars; the UI hides the section).
    * ``public_key`` — VAPID public key the browser passes to
      ``PushManager.subscribe({applicationServerKey: ...})``.  Empty
      when ``enabled`` is False.
    * ``subscribed`` — whether at least one ``PushSubscription``
      row exists for this user across all devices.  The SPA only
      tracks "subscribed on THIS browser" client-side via
      ``localStorage`` — this flag is the cross-device server view
      used for the UI badge ("subscribed on N devices").
    * ``device_count`` — how many distinct subscriptions this user
      has on file.
    """

    model_config = ConfigDict(extra="forbid")

    enabled:      bool
    public_key:   str
    subscribed:   bool
    device_count: int


class PushSubscribeRequest(BaseModel):
    """Body for ``POST /api/v2/push/subscribe`` — the envelope the
    browser returns from ``PushManager.subscribe()`` flattened into
    its three relevant fields.

    * ``endpoint`` — push provider URL the server delivers to.
      Cap at 2KB; FCM endpoints are ~200 chars but the spec doesn't
      pin an upper bound.
    * ``p256dh`` — base64-URL public key the browser generated for
      the subscription.  Used to encrypt the payload.
    * ``auth``  — base64-URL auth secret, also from the browser.
    * ``user_agent`` — optional UA string for the "manage devices"
      UI follow-up (currently unused but cheap to capture).
    """

    model_config = ConfigDict(extra="forbid")

    endpoint:   str = Field(..., min_length=10, max_length=2000)
    p256dh:     str = Field(..., min_length=10, max_length=200)
    auth:       str = Field(..., min_length=4,  max_length=80)
    user_agent: str = Field("", max_length=255)


class PushUnsubscribeRequest(BaseModel):
    """Body for ``DELETE /api/v2/push/subscribe`` — identify
    which subscription to drop by its endpoint URL.

    Endpoint is the only field PushManager exposes that's
    stable + unique across the subscription's lifetime, so the
    SPA always has it.
    """

    model_config = ConfigDict(extra="forbid")

    endpoint: str = Field(..., min_length=10, max_length=2000)
