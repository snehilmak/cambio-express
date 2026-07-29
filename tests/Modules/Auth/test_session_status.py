"""Endpoint tests for ``GET /auth/session-status`` (PR C).

The SPA shell calls this on load to decide whether to gate the user
out to a re-subscribe / suspended screen. Every authed role can call
it. Read-only — no login/token logic touched.
"""
from tests._app import db, db_session
from tests.conftest import login_admin, login_superadmin


def _headers(token):
    return {"Authorization": f"Bearer {token}"}


def _set_store(store_id, **fields):
    from api.Modules.Tenancy.Models import Store
    with db_session():
        s = db.session.get(Store, store_id)
        for k, v in fields.items():
            setattr(s, k, v)
        db.session.commit()


def test_active_trial_store_not_gated(client, test_store_id):
    # Seeded test store is a trial ending in +7 days → active.
    token = login_admin(client, test_store_id)
    resp = client.get("/api/v2/auth/session-status", headers=_headers(token))
    assert resp.status_code == 200
    body = resp.json()
    assert body["gated"] is False
    assert body["reason"] == ""


def test_inactive_plan_store_is_subscription_gated(client, test_store_id):
    _set_store(test_store_id, plan="inactive")
    token = login_admin(client, test_store_id)
    resp = client.get("/api/v2/auth/session-status", headers=_headers(token))
    assert resp.status_code == 200
    body = resp.json()
    assert body["gated"] is True
    assert body["reason"] == "subscription"
    assert body["plan"] == "inactive"


def test_frozen_store_is_frozen_gated(client, test_store_id):
    from api.Core.Clock import utc_now
    _set_store(test_store_id, frozen_at=utc_now(), frozen_reason="abuse")
    token = login_admin(client, test_store_id)
    resp = client.get("/api/v2/auth/session-status", headers=_headers(token))
    assert resp.status_code == 200
    body = resp.json()
    assert body["gated"] is True
    assert body["reason"] == "frozen"
    # The operator reason is NOT surfaced to the store's users.
    assert "abuse" not in resp.text


def test_superadmin_never_gated(client, test_store_id):
    # Even if a store is frozen, the superadmin (no store scope) is not
    # gated — they operate the platform.
    from api.Core.Clock import utc_now
    _set_store(test_store_id, frozen_at=utc_now())
    token = login_superadmin(client)
    resp = client.get("/api/v2/auth/session-status", headers=_headers(token))
    assert resp.status_code == 200
    assert resp.json()["gated"] is False


def test_requires_auth(client):
    resp = client.get("/api/v2/auth/session-status")
    assert resp.status_code in (401, 403)
