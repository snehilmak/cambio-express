"""Tests for Stripe webhook → data retention lifecycle (CLAUDE.md #4).

- `customer.subscription.deleted` => plan=inactive, stripe_subscription_id="",
  canceled_at=now, data_retention_until = now + DATA_RETENTION_DAYS (180).
- `checkout.session.completed` on a returning store => clears canceled_at
  and data_retention_until (they're coming back — don't delete their data).
- Unhandled event types => 200 OK, no DB mutation.
- Price-ID lookup failure falls back to "pro" (safest: keep their access on).
"""
import json
import os
from datetime import datetime, timedelta
from unittest.mock import patch

# Resolved at call time (not import time) — CI passes different price IDs
# than conftest, and the webhook reads the env var live.
def _basic_price_id():
    return os.environ.get("STRIPE_BASIC_PRICE_ID", "price_basic_test")


def _seed(plan="pro", **kwargs):
    from app import db, Store
    s = Store(name="Retention Store", slug="retention-store",
              email="r@test.com", plan=plan, **kwargs)
    db.session.add(s); db.session.commit()
    return s.id


def _post(client, event):
    """POST a webhook event with a mocked signature check."""
    with patch("stripe.Webhook.construct_event", return_value=event):
        return client.post(
            "/webhooks/stripe",
            data=json.dumps(event).encode(),
            headers={"Stripe-Signature": "valid",
                     "Content-Type": "application/json"},
        )


# ── customer.subscription.deleted ───────────────────────────────────────────

def test_deleted_starts_180_day_retention(client):
    from app import db, Store, DATA_RETENTION_DAYS
    with client.application.app_context():
        sid = _seed(plan="pro", stripe_subscription_id="sub_xyz")
    before = datetime.utcnow()
    resp = _post(client, {
        "type": "customer.subscription.deleted",
        "data": {"object": {"id": "sub_xyz"}},
    })
    after = datetime.utcnow()
    assert resp.status_code == 200
    with client.application.app_context():
        s = db.session.get(Store, sid)
        assert s.plan == "inactive"
        assert s.stripe_subscription_id == ""
        assert s.canceled_at is not None
        assert before <= s.canceled_at <= after
        assert s.data_retention_until is not None
        # 180 days from canceled_at — allow small runtime slack.
        expected = s.canceled_at + timedelta(days=DATA_RETENTION_DAYS)
        assert abs((s.data_retention_until - expected).total_seconds()) < 2
        assert DATA_RETENTION_DAYS == 180


def test_deleted_event_for_unknown_subscription_is_noop(client):
    """Stripe can send us deletions for subs we never tracked — must not 500."""
    from app import db, Store
    with client.application.app_context():
        sid = _seed(plan="pro", stripe_subscription_id="sub_ours")
    resp = _post(client, {
        "type": "customer.subscription.deleted",
        "data": {"object": {"id": "sub_not_ours"}},
    })
    assert resp.status_code == 200
    with client.application.app_context():
        s = db.session.get(Store, sid)
        assert s.plan == "pro"  # unchanged
        assert s.data_retention_until is None


# ── checkout.session.completed (returning customer) ─────────────────────────

def test_checkout_completed_clears_retention_timer(client):
    """Returning customer: clear canceled_at + data_retention_until."""
    from app import db, Store
    past_cancel = datetime.utcnow() - timedelta(days=30)
    retain_until = datetime.utcnow() + timedelta(days=150)
    with client.application.app_context():
        sid = _seed(plan="inactive",
                    canceled_at=past_cancel,
                    data_retention_until=retain_until,
                    stripe_customer_id="cus_return")
    event = {
        "type": "checkout.session.completed",
        "data": {"object": {
            "metadata": {"store_id": str(sid)},
            "customer": "cus_return",
            "subscription": "sub_new",
        }},
    }
    mock_sub = {"items": {"data": [{"price": {"id": _basic_price_id()}}]}}
    with patch("stripe.Subscription.retrieve", return_value=mock_sub):
        resp = _post(client, event)
    assert resp.status_code == 200
    with client.application.app_context():
        s = db.session.get(Store, sid)
        assert s.plan == "basic"
        assert s.canceled_at is None
        assert s.data_retention_until is None
        assert s.stripe_subscription_id == "sub_new"


def test_checkout_completed_maps_basic_price_to_basic_plan(client):
    from app import db, Store
    with client.application.app_context():
        sid = _seed(plan="trial")
    event = {
        "type": "checkout.session.completed",
        "data": {"object": {
            "metadata": {"store_id": str(sid)},
            "customer": "cus_1",
            "subscription": "sub_1",
        }},
    }
    mock_sub = {"items": {"data": [{"price": {"id": _basic_price_id()}}]}}
    with patch("stripe.Subscription.retrieve", return_value=mock_sub):
        _post(client, event)
    with client.application.app_context():
        assert db.session.get(Store, sid).plan == "basic"


def test_checkout_completed_non_basic_price_maps_to_pro(client):
    """Any non-basic price id routes to 'pro' (covers monthly + yearly pro)."""
    from app import db, Store
    with client.application.app_context():
        sid = _seed(plan="trial")
    event = {
        "type": "checkout.session.completed",
        "data": {"object": {
            "metadata": {"store_id": str(sid)},
            "customer": "cus_1",
            "subscription": "sub_1",
        }},
    }
    mock_sub = {"items": {"data": [{"price": {"id": "price_pro_yearly_test"}}]}}
    with patch("stripe.Subscription.retrieve", return_value=mock_sub):
        _post(client, event)
    with client.application.app_context():
        assert db.session.get(Store, sid).plan == "pro"


def test_checkout_completed_falls_back_to_pro_on_retrieve_failure(client):
    """If stripe.Subscription.retrieve() blows up we still grant pro access.

    Better to give them too much than to lock a paying customer out.
    """
    from app import db, Store
    with client.application.app_context():
        sid = _seed(plan="trial")
    event = {
        "type": "checkout.session.completed",
        "data": {"object": {
            "metadata": {"store_id": str(sid)},
            "customer": "cus_1",
            "subscription": "sub_1",
        }},
    }
    with patch("stripe.Subscription.retrieve",
               side_effect=Exception("stripe boom")):
        resp = _post(client, event)
    assert resp.status_code == 200
    with client.application.app_context():
        s = db.session.get(Store, sid)
        assert s.plan == "pro"
        assert s.stripe_subscription_id == "sub_1"


def test_checkout_completed_ignored_without_store_id_metadata(client):
    """No metadata.store_id => must not mutate anything (or 500)."""
    from app import db, Store
    with client.application.app_context():
        sid = _seed(plan="trial")
    event = {
        "type": "checkout.session.completed",
        "data": {"object": {
            "metadata": {},
            "customer": "cus_unknown",
            "subscription": "sub_unknown",
        }},
    }
    mock_sub = {"items": {"data": [{"price": {"id": "price_pro_test"}}]}}
    with patch("stripe.Subscription.retrieve", return_value=mock_sub):
        resp = _post(client, event)
    assert resp.status_code == 200
    with client.application.app_context():
        assert db.session.get(Store, sid).plan == "trial"


def test_checkout_completed_ignored_for_unknown_store_id(client):
    """metadata.store_id points to a store that no longer exists — just 200."""
    event = {
        "type": "checkout.session.completed",
        "data": {"object": {
            "metadata": {"store_id": "999999"},
            "customer": "cus_ghost",
            "subscription": "sub_ghost",
        }},
    }
    mock_sub = {"items": {"data": [{"price": {"id": "price_basic_test"}}]}}
    with patch("stripe.Subscription.retrieve", return_value=mock_sub):
        resp = _post(client, event)
    assert resp.status_code == 200


# ── Unhandled events / bad signatures ───────────────────────────────────────

def test_unhandled_event_type_returns_200_without_mutation(client):
    from app import db, Store
    with client.application.app_context():
        sid = _seed(plan="pro")
    resp = _post(client, {
        "type": "invoice.payment_succeeded",  # not handled by our webhook
        "data": {"object": {}},
    })
    assert resp.status_code == 200
    with client.application.app_context():
        s = db.session.get(Store, sid)
        assert s.plan == "pro"
        assert s.data_retention_until is None


def test_webhook_rejects_bad_signature_without_patching(client):
    """Without mocking construct_event, signature verification must fail."""
    resp = client.post(
        "/webhooks/stripe",
        data=b'{"type":"checkout.session.completed"}',
        headers={"Stripe-Signature": "t=0,v1=deadbeef",
                 "Content-Type": "application/json"},
    )
    assert resp.status_code == 400
