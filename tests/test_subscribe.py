def test_subscribe_requires_login(client):
    resp = client.get("/subscribe", follow_redirects=False)
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]

def test_subscribe_loads_for_logged_in_user(logged_in_client):
    resp = logged_in_client.get("/subscribe")
    assert resp.status_code == 200
    assert b"$20" in resp.data
    assert b"$30" in resp.data
    assert b"Basic" in resp.data
    assert b"Pro" in resp.data

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

def test_subscribe_success_loads(logged_in_client):
    resp = logged_in_client.get("/subscribe/success")
    assert resp.status_code == 200
    assert b"payment" in resp.data.lower() or b"plan" in resp.data.lower()

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
        s = Store.query.get(sid)
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
        s = Store.query.get(sid)
        assert s.plan == "inactive"
        assert s.stripe_subscription_id == ""
