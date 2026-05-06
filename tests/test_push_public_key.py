"""Regression: /api/push/public-key should never 501.

Before this fix the endpoint returned 501 whenever VAPID wasn't configured,
which filled every user's console with a red error on every page view.
It now returns 200 with key=null and the client hides the opt-in UI.

The VAPID values now live in
`api.Modules.Notifications.Services.push` (PR 67); the legacy
`app.VAPID_*` constants are re-exports for back-compat. Tests
patch both modules so the public-key route + `push_enabled()`
stay aligned.
"""


def _set_vapid(monkeypatch, *, public, private):
    """Patch both the legacy app-module names + the Service's
    canonical constants so route reads stay aligned."""
    monkeypatch.setattr("app.VAPID_PUBLIC_KEY", public)
    monkeypatch.setattr("app.VAPID_PRIVATE_KEY", private)
    monkeypatch.setattr(
        "api.Modules.Notifications.Services.push.VAPID_PUBLIC_KEY",
        public,
    )
    monkeypatch.setattr(
        "api.Modules.Notifications.Services.push.VAPID_PRIVATE_KEY",
        private,
    )


def test_push_public_key_returns_null_when_vapid_unset(client, monkeypatch):
    # Belt and suspenders — ensure VAPID isn't set for this test.
    _set_vapid(monkeypatch, public="", private="")
    resp = client.get("/api/push/public-key")
    assert resp.status_code == 200
    assert resp.get_json() == {"key": None}


def test_push_public_key_returns_key_when_vapid_set(client, monkeypatch):
    _set_vapid(monkeypatch, public="BVapidPubKey123", private="vapid-priv")
    resp = client.get("/api/push/public-key")
    assert resp.status_code == 200
    assert resp.get_json() == {"key": "BVapidPubKey123"}
