"""HTTP integration tests for the push-subscription endpoints.

  GET    /api/v2/auth/push/status      → status payload
  POST   /api/v2/auth/push/subscribe   → register a subscription
  DELETE /api/v2/auth/push/subscribe   → drop a subscription

Auth gating: every route requires a valid JWT. The subscription
rows are scoped to ``claims["sub"]`` (the authenticated user).
"""
from tests._app import db, db_session


def _login(client_, store_id):
    resp = client_.post(
        "/api/v2/auth/login",
        json={
            "username": "admin@test.com",
            "password": "testpass123!",
            "store_id": store_id,
        },
    )
    return resp.get_json()["access_token"]


def _enable_vapid(monkeypatch):
    """Force the push module to look enabled so the controller's
    409 gate doesn't fire.  Tests that exercise the gate skip
    this helper."""
    import api.Modules.Notifications.Services.push as push_mod
    monkeypatch.setattr(push_mod, "VAPID_PUBLIC_KEY",  "TEST_PUB_KEY")
    monkeypatch.setattr(push_mod, "VAPID_PRIVATE_KEY", "TEST_PRIV_KEY")


# ── Auth gating ────────────────────────────────────────────


def test_status_requires_jwt(client):
    resp = client.get("/api/v2/auth/push/status")
    assert resp.status_code == 401


def test_subscribe_requires_jwt(client):
    resp = client.post(
        "/api/v2/auth/push/subscribe",
        json={
            "endpoint": "https://example.com/push/abc",
            "p256dh":   "AAAA" * 22,
            "auth":     "AAAA" * 5,
        },
    )
    assert resp.status_code == 401


# ── Status payload ────────────────────────────────────────


def test_status_shows_disabled_when_vapid_missing(client, test_store_id):
    """Without VAPID keys the channel is server-disabled and the
    public key comes back empty."""
    token = _login(client, test_store_id)
    resp = client.get(
        "/api/v2/auth/push/status",
        headers={"Authorization": f"Bearer {token}"},
    )
    body = resp.get_json()
    assert resp.status_code == 200
    assert body["enabled"] is False
    assert body["public_key"] == ""
    assert body["subscribed"] is False
    assert body["device_count"] == 0


def test_status_shows_enabled_with_vapid(
    client, test_store_id, monkeypatch,
):
    _enable_vapid(monkeypatch)
    token = _login(client, test_store_id)
    body = client.get(
        "/api/v2/auth/push/status",
        headers={"Authorization": f"Bearer {token}"},
    ).get_json()
    assert body["enabled"] is True
    assert body["public_key"] == "TEST_PUB_KEY"


# ── Subscribe gate ────────────────────────────────────────


def test_subscribe_409_when_push_disabled(client, test_store_id):
    """Without VAPID keys configured the endpoint refuses to store
    a row — keeps the SPA from silently registering subscriptions
    we couldn't deliver on."""
    token = _login(client, test_store_id)
    resp = client.post(
        "/api/v2/auth/push/subscribe",
        json={
            "endpoint": "https://example.com/push/abc",
            "p256dh":   "AAAA" * 22,
            "auth":     "AAAA" * 5,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 409


# ── CRUD happy path ───────────────────────────────────────


def test_subscribe_then_status_then_unsubscribe(
    client, test_store_id, monkeypatch,
):
    _enable_vapid(monkeypatch)
    token = _login(client, test_store_id)
    headers = {"Authorization": f"Bearer {token}"}

    # Subscribe.
    body = client.post(
        "/api/v2/auth/push/subscribe",
        json={
            "endpoint": "https://fcm.example/abc",
            "p256dh":   "AAAA" * 22,
            "auth":     "AAAA" * 5,
            "user_agent": "Chrome on macOS",
        },
        headers=headers,
    ).get_json()
    assert body["subscribed"] is True
    assert body["device_count"] == 1

    # Status reflects the subscription.
    body = client.get(
        "/api/v2/auth/push/status", headers=headers,
    ).get_json()
    assert body["subscribed"] is True
    assert body["device_count"] == 1

    # Idempotent re-subscribe on the SAME endpoint updates in place.
    body = client.post(
        "/api/v2/auth/push/subscribe",
        json={
            "endpoint": "https://fcm.example/abc",
            "p256dh":   "BBBB" * 22,
            "auth":     "BBBB" * 5,
            "user_agent": "Chrome on macOS (refresh)",
        },
        headers=headers,
    ).get_json()
    assert body["device_count"] == 1, "re-subscribe shouldn't add a row"

    # Subscribe a SECOND device → row count bumps to 2.
    body = client.post(
        "/api/v2/auth/push/subscribe",
        json={
            "endpoint": "https://fcm.example/def",
            "p256dh":   "CCCC" * 22,
            "auth":     "CCCC" * 5,
        },
        headers=headers,
    ).get_json()
    assert body["device_count"] == 2

    # Unsubscribe the first endpoint → 1 remaining.
    resp = client.delete(
        "/api/v2/auth/push/subscribe",
        json={"endpoint": "https://fcm.example/abc"},
        headers=headers,
    )
    body = resp.get_json()
    assert resp.status_code == 200
    assert body["device_count"] == 1
    assert body["subscribed"] is True  # still has the 2nd one

    # Idempotent unsubscribe — second DELETE returns 200 with the
    # same state, not a 404.
    body = client.delete(
        "/api/v2/auth/push/subscribe",
        json={"endpoint": "https://fcm.example/abc"},
        headers=headers,
    ).get_json()
    assert body["device_count"] == 1


def test_subscribe_isolates_users(
    client, test_store_id, monkeypatch,
):
    """A subscription registered by admin A doesn't show up in
    admin B's status payload."""
    _enable_vapid(monkeypatch)
    with db_session():
        from api.Modules.Tenancy.Models import User
        b = User(
            store_id=test_store_id, username="push-admin-b@test.com",
            full_name="Admin B", role="admin",
        )
        b.set_password("testpass123!")
        db.session.add(b); db.session.commit()
    token_a = _login(client, test_store_id)
    token_b = client.post(
        "/api/v2/auth/login",
        json={
            "username": "push-admin-b@test.com",
            "password": "testpass123!",
            "store_id": test_store_id,
        },
    ).get_json()["access_token"]

    client.post(
        "/api/v2/auth/push/subscribe",
        json={
            "endpoint": "https://fcm.example/alpha",
            "p256dh":   "AAAA" * 22,
            "auth":     "AAAA" * 5,
        },
        headers={"Authorization": f"Bearer {token_a}"},
    )

    body_b = client.get(
        "/api/v2/auth/push/status",
        headers={"Authorization": f"Bearer {token_b}"},
    ).get_json()
    assert body_b["subscribed"] is False
    assert body_b["device_count"] == 0
