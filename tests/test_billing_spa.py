"""Billing SPA migration contract tests.

The /subscribe pricing page and the /admin/subscription tabbed
billing page both 301 to React. The SPA fetches:

  - Subscribe.tsx → static plan tiles, then /api/v2/billing/checkout
  - AdminSubscription.tsx → /api/v2/admin/subscription for the
    page state, /api/v2/billing/portal for Manage / Cancel actions,
    and /api/v2/admin/addons/<key>/toggle for add-on flips.

Two Jinja templates retired (admin_subscription.html, subscribe.html).
"""
from tests._app import db


def _admin_session_login(client, store_id):
    from api.Modules.Tenancy.Models import Store, User
    from tests._app import db
    with client.application.app_context():
        u = db.session.query(User).filter_by(store_id=store_id, role="admin").first()
        uid = u.id
        s = db.session.get(Store, store_id)
        s.plan = "pro"
        s.billing_cycle = "monthly"
        db.session.commit()


def _admin_jwt(client, store_id):
    return client.post(
        "/api/v2/auth/login",
        json={"username": "admin@test.com", "password": "testpass123!",
              "store_id": store_id},
    ).get_json()["access_token"]


# ── Legacy redirects ─────────────────────────────────────────


def test_subscribe_redirects_to_spa(logged_in_client):
    resp = logged_in_client.get("/subscribe", follow_redirects=False)
    assert resp.status_code == 301
    assert resp.headers["Location"] == "/app/subscribe"


def test_admin_subscription_redirects_to_spa(logged_in_client):
    resp = logged_in_client.get("/admin/subscription", follow_redirects=False)
    assert resp.status_code == 301
    assert resp.headers["Location"] == "/app/admin/subscription"


# ── /api/v2/admin/subscription envelope ──────────────────────


def test_subscription_summary_envelope(client, test_store_id):
    _admin_session_login(client, test_store_id)
    jwt = _admin_jwt(client, test_store_id)
    resp = client.get(
        "/api/v2/admin/subscription",
        headers={"Authorization": f"Bearer {jwt}"},
    )
    assert resp.status_code == 200, resp.get_data(as_text=True)
    body = resp.get_json()
    for k in ("store", "plan_label", "plan_price", "has_paid_plan",
              "trial_status", "trial_days_left", "retention_days_left",
              "retention_total_days", "addons", "active_addon_count"):
        assert k in body, f"missing {k}"
    assert body["plan_label"] == "Pro"
    assert body["plan_price"] == "$45 / month"
    assert body["has_paid_plan"] is True
    assert isinstance(body["addons"], list)


def test_subscription_summary_trial_store_shows_trial_state(
    client, test_store_id,
):
    """Default test store is on a trial. Expose trial_status +
    trial_days_left for the SPA's plan-hero meta line."""
    from api.Modules.Tenancy.Models import Store
    from tests._app import db
    with client.application.app_context():
        s = db.session.get(Store, test_store_id)
        s.plan = "trial"
        db.session.commit()
    _admin_session_login(client, test_store_id)
    # Re-set plan back to trial after admin_session_login flipped it.
    with client.application.app_context():
        s = db.session.get(Store, test_store_id)
        s.plan = "trial"
        db.session.commit()
    jwt = _admin_jwt(client, test_store_id)
    resp = client.get(
        "/api/v2/admin/subscription",
        headers={"Authorization": f"Bearer {jwt}"},
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["plan_label"] == "Free Trial"
    # trial_status reflects active / expiring_soon / grace / expired.
    assert body["trial_status"] in (
        "active", "expiring_soon", "grace", "expired",
    )


def test_subscription_summary_requires_auth(client):
    resp = client.get("/api/v2/admin/subscription")
    assert resp.status_code == 401
