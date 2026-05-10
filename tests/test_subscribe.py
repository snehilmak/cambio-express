def test_subscribe_requires_login(client):
    resp = client.get("/subscribe", follow_redirects=False)
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]

def test_subscribe_redirects_to_spa_for_logged_in_user(logged_in_client):
    """The /subscribe pricing page moved to React (Subscribe.tsx).
    Authed callers get a 301 to /app/subscribe; the SPA reads the
    plan tiles from a static list and POSTs /api/v2/billing/checkout
    to mint a Stripe Checkout Session."""
    resp = logged_in_client.get("/subscribe", follow_redirects=False)
    assert resp.status_code == 301
    assert resp.headers["Location"] == "/app/subscribe"

from unittest.mock import patch, MagicMock

def test_checkout_rejects_invalid_plan(logged_in_client):
    resp = logged_in_client.post("/subscribe/checkout",
                                  data={"plan": "enterprise"},
                                  follow_redirects=False)
    # Must not redirect to Stripe
    if resp.status_code == 302:
        assert "stripe.com" not in resp.headers.get("Location", "")

def test_checkout_redirects_to_stripe_for_basic(logged_in_client):
    mock_session = MagicMock()
    mock_session.url = "https://checkout.stripe.com/test-basic"
    with patch("stripe.checkout.Session.create", return_value=mock_session):
        resp = logged_in_client.post("/subscribe/checkout",
                                      data={"plan": "basic"},
                                      follow_redirects=False)
    assert resp.status_code == 303
    assert "stripe.com" in resp.headers["Location"]

def test_checkout_redirects_to_stripe_for_pro(logged_in_client):
    mock_session = MagicMock()
    mock_session.url = "https://checkout.stripe.com/test-pro"
    with patch("stripe.checkout.Session.create", return_value=mock_session):
        resp = logged_in_client.post("/subscribe/checkout",
                                      data={"plan": "pro"},
                                      follow_redirects=False)
    assert resp.status_code == 303
    assert "stripe.com" in resp.headers["Location"]

def test_checkout_redirects_to_stripe_for_basic_yearly(logged_in_client, monkeypatch):
    """Basic yearly uses its own Stripe Price ID — conftest seeds only the
    monthly one, so we set the yearly env var inline for this test."""
    monkeypatch.setenv("STRIPE_BASIC_YEARLY_PRICE_ID", "price_basic_yearly_test")
    mock_session = MagicMock()
    mock_session.url = "https://checkout.stripe.com/test-basic-yearly"
    with patch("stripe.checkout.Session.create", return_value=mock_session) as m:
        resp = logged_in_client.post("/subscribe/checkout",
                                      data={"plan": "basic_yearly"},
                                      follow_redirects=False)
    assert resp.status_code == 303
    assert "stripe.com" in resp.headers["Location"]
    line_items = m.call_args.kwargs["line_items"]
    assert line_items[0]["price"] == "price_basic_yearly_test"


def test_webhook_maps_basic_yearly_price_to_basic_plan(client, monkeypatch):
    """The yearly Basic price ID must land on Store.plan='basic', not 'pro'.
    Before PR #58 the webhook treated anything that wasn't the monthly
    Basic price as 'pro', which would've silently upgraded yearly Basic
    subscribers."""
    from app import db, Store
    monkeypatch.setenv("STRIPE_BASIC_YEARLY_PRICE_ID", "price_basic_yearly_test")
    with client.application.app_context():
        s = Store(name="Yearly Basic", slug="yearly-basic",
                  email="yb@test.com", plan="trial",
                  stripe_customer_id="cus_yb")
        db.session.add(s)
        db.session.commit()
        sid = s.id

    event_payload = {
        "type": "checkout.session.completed",
        "data": {"object": {
            "metadata": {"store_id": str(sid)},
            "customer": "cus_yb",
            "subscription": "sub_yb",
        }}
    }
    mock_sub = {"items": {"data": [{"price": {"id": "price_basic_yearly_test"}}]}}
    with patch("stripe.Webhook.construct_event", return_value=event_payload), \
         patch("stripe.Subscription.retrieve", return_value=mock_sub):
        resp = client.post("/webhooks/stripe",
                           data=json.dumps(event_payload).encode(),
                           headers={"Stripe-Signature": "valid",
                                    "Content-Type": "application/json"})
    assert resp.status_code == 200
    with client.application.app_context():
        assert db.session.get(Store, sid).plan == "basic"


def test_checkout_redirects_to_stripe_for_pro_yearly(logged_in_client, monkeypatch):
    # Yearly Pro uses its own Stripe Price ID; the conftest seeds only the
    # monthly one, so we set the yearly env var inline for this test.
    monkeypatch.setenv("STRIPE_PRO_YEARLY_PRICE_ID", "price_pro_yearly_test")
    mock_session = MagicMock()
    mock_session.url = "https://checkout.stripe.com/test-pro-yearly"
    with patch("stripe.checkout.Session.create", return_value=mock_session) as m:
        resp = logged_in_client.post("/subscribe/checkout",
                                      data={"plan": "pro_yearly"},
                                      follow_redirects=False)
    assert resp.status_code == 303
    assert "stripe.com" in resp.headers["Location"]
    # Confirm the yearly Price ID was passed to Stripe (not the monthly one).
    line_items = m.call_args.kwargs["line_items"]
    assert line_items[0]["price"] == "price_pro_yearly_test"

def test_subscribe_success_redirects_to_app(logged_in_client):
    """Page rendering moved to React (/app/subscribe/success). The
    Flask handler is now a 301 so Stripe's success_url chain still
    lands on a working page, and the SPA polls store-info to flip
    'Payment received' → 'You're on Basic/Pro' without a refresh."""
    resp = logged_in_client.get("/subscribe/success", follow_redirects=False)
    assert resp.status_code == 301
    assert resp.headers["Location"] == "/app/subscribe/success"

import json

def test_webhook_rejects_invalid_signature(client):
    resp = client.post("/webhooks/stripe",
                       data=b'{"type":"checkout.session.completed"}',
                       headers={"Stripe-Signature": "bad",
                                "Content-Type": "application/json"})
    assert resp.status_code == 400

def test_webhook_checkout_completed_updates_plan(client):
    from app import db, Store
    from unittest.mock import patch
    with client.application.app_context():
        s = Store(name="Webhook Store", slug="webhook-store",
                  email="webhook@test.com", plan="trial",
                  stripe_customer_id="cus_test123")
        db.session.add(s)
        db.session.commit()
        sid = s.id

    event_payload = {
        "type": "checkout.session.completed",
        "data": {"object": {
            "metadata": {"store_id": str(sid)},
            "customer": "cus_test123",
            "subscription": "sub_test456",
        }}
    }
    mock_sub = {"items": {"data": [{"price": {"id": "price_pro_test"}}]}}

    with patch("stripe.Webhook.construct_event", return_value=event_payload), \
         patch("stripe.Subscription.retrieve", return_value=mock_sub):
        resp = client.post("/webhooks/stripe",
                           data=json.dumps(event_payload).encode(),
                           headers={"Stripe-Signature": "valid",
                                    "Content-Type": "application/json"})

    assert resp.status_code == 200
    with client.application.app_context():
        s = db.session.get(Store, sid)
        assert s.plan == "pro"
        assert s.stripe_subscription_id == "sub_test456"

def test_webhook_subscription_deleted_sets_inactive(client):
    from app import db, Store
    from unittest.mock import patch
    with client.application.app_context():
        s = Store(name="Cancel Store", slug="cancel-store",
                  email="cancel@test.com", plan="pro",
                  stripe_subscription_id="sub_cancel789")
        db.session.add(s)
        db.session.commit()
        sid = s.id

    event_payload = {
        "type": "customer.subscription.deleted",
        "data": {"object": {"id": "sub_cancel789"}}
    }
    with patch("stripe.Webhook.construct_event", return_value=event_payload):
        resp = client.post("/webhooks/stripe",
                           data=json.dumps(event_payload).encode(),
                           headers={"Stripe-Signature": "valid",
                                    "Content-Type": "application/json"})

    assert resp.status_code == 200
    with client.application.app_context():
        s = db.session.get(Store, sid)
        assert s.plan == "inactive"
        assert s.stripe_subscription_id == ""
