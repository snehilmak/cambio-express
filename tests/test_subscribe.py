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
