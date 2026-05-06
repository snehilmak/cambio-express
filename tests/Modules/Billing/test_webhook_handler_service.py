"""Unit tests for Billing.Services.webhook.handle_stripe_event (PR 59).

The orchestrator dispatches verified Stripe events to the right
side-effect flow. Tests stub `stripe.Subscription.retrieve` and
the downstream Services we already trust (clear_cancellation_state,
ensure_referral_code, apply_pending_referral_credits,
apply_subscription_cancelled, find_store_by_subscription_id).
"""
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest


def _checkout_event(*, store_id="42", subscription="sub_123",
                    customer="cus_123"):
    """Stripe `checkout.session.completed` event shape."""
    return {
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "metadata": {"store_id": store_id} if store_id else {},
                "subscription": subscription,
                "customer": customer,
            },
        },
    }


def _subscription_deleted_event(*, sub_id="sub_123"):
    """Stripe `customer.subscription.deleted` event shape."""
    return {
        "type": "customer.subscription.deleted",
        "data": {"object": {"id": sub_id}},
    }


# ── checkout.session.completed ─────────────────────────────


def test_checkout_completed_no_store_id_in_metadata_is_noop():
    """Missing metadata.store_id → bail. Some payment links don't
    set metadata; we don't want to crash on those."""
    from api.Modules.Billing.Services import handle_stripe_event
    db = MagicMock()
    handle_stripe_event(db, _checkout_event(store_id=""))
    assert db.commit.call_count == 0


def test_checkout_completed_store_not_found_is_noop():
    """metadata.store_id set, but the store row was deleted in the
    interim. Bail without a 500."""
    from api.Modules.Billing.Services import handle_stripe_event
    db = MagicMock()
    db.get.return_value = None
    handle_stripe_event(db, _checkout_event())
    assert db.commit.call_count == 0


def test_checkout_completed_happy_path(monkeypatch):
    """All Services + Stripe SDK behave: plan flips, IDs persist,
    cancellation state clears, referral hooks run, commit fires."""
    import stripe
    import api.Modules.Billing.Services.webhook as wh
    # Pin the price → ('basic', 'monthly') so we can assert.
    monkeypatch.setattr(
        wh, "derive_plan_from_price",
        MagicMock(return_value=("basic", "monthly")),
    )
    monkeypatch.setattr(
        wh, "clear_cancellation_state", MagicMock(),
    )
    monkeypatch.setattr(
        wh, "ensure_referral_code", MagicMock(),
    )
    monkeypatch.setattr(
        wh, "apply_pending_referral_credits", MagicMock(),
    )
    monkeypatch.setattr(
        stripe.Subscription, "retrieve",
        MagicMock(return_value={
            "items": {"data": [{"price": {"id": "price_basic_monthly"}}]},
        }),
    )

    db = MagicMock()
    store = MagicMock()
    store.id = 42
    db.get.return_value = store

    wh.handle_stripe_event(db, _checkout_event())

    assert store.plan == "basic"
    assert store.billing_cycle == "monthly"
    assert store.stripe_customer_id == "cus_123"
    assert store.stripe_subscription_id == "sub_123"
    wh.clear_cancellation_state.assert_called_once_with(store)
    wh.ensure_referral_code.assert_called_once_with(db, store)
    wh.apply_pending_referral_credits.assert_called_once_with(db, store)
    assert db.commit.call_count >= 1


def test_checkout_completed_stripe_sub_retrieve_failure_falls_back(monkeypatch):
    """Stripe.Subscription.retrieve raising must NOT fail the
    webhook — fall back to ('pro', 'monthly') so the user gets
    access while the operator investigates."""
    import stripe
    import api.Modules.Billing.Services.webhook as wh
    monkeypatch.setattr(
        stripe.Subscription, "retrieve",
        MagicMock(side_effect=RuntimeError("Stripe down")),
    )
    monkeypatch.setattr(wh, "clear_cancellation_state", MagicMock())
    monkeypatch.setattr(wh, "ensure_referral_code", MagicMock())
    monkeypatch.setattr(wh, "apply_pending_referral_credits", MagicMock())

    db = MagicMock()
    store = MagicMock()
    store.id = 42
    db.get.return_value = store

    wh.handle_stripe_event(db, _checkout_event())

    assert store.plan == "pro"
    assert store.billing_cycle == "monthly"
    # Plan flip still committed.
    assert db.commit.call_count >= 1


def test_checkout_completed_referral_failure_does_not_block_plan_flip(monkeypatch):
    """A failure in the referral side-effects must NOT roll back
    the plan flip. We log and proceed."""
    import stripe
    import api.Modules.Billing.Services.webhook as wh
    monkeypatch.setattr(
        wh, "derive_plan_from_price",
        MagicMock(return_value=("pro", "yearly")),
    )
    monkeypatch.setattr(wh, "clear_cancellation_state", MagicMock())
    # Referral mint blows up.
    monkeypatch.setattr(
        wh, "ensure_referral_code",
        MagicMock(side_effect=RuntimeError("referral table missing")),
    )
    monkeypatch.setattr(
        wh, "apply_pending_referral_credits", MagicMock(),
    )
    monkeypatch.setattr(
        stripe.Subscription, "retrieve",
        MagicMock(return_value={
            "items": {"data": [{"price": {"id": "price_pro_yearly"}}]},
        }),
    )

    db = MagicMock()
    store = MagicMock()
    store.id = 42
    db.get.return_value = store

    wh.handle_stripe_event(db, _checkout_event())

    # Plan flip stuck.
    assert store.plan == "pro"
    assert store.billing_cycle == "yearly"
    assert db.commit.call_count >= 1


# ── customer.subscription.deleted ──────────────────────────


def test_subscription_deleted_marks_store_inactive(monkeypatch):
    import api.Modules.Billing.Services.webhook as wh
    store = MagicMock()
    monkeypatch.setattr(
        wh, "find_store_by_subscription_id",
        MagicMock(return_value=store),
    )
    monkeypatch.setattr(
        wh, "apply_subscription_cancelled", MagicMock(),
    )
    db = MagicMock()
    wh.handle_stripe_event(
        db, _subscription_deleted_event(), retention_days=180,
    )
    wh.apply_subscription_cancelled.assert_called_once_with(
        store, retention_days=180,
    )
    assert db.commit.call_count == 1


def test_subscription_deleted_no_matching_store_is_noop(monkeypatch):
    """Webhook for a subscription created in a sandbox / different
    Stripe mode that we don't have a store for. Bail without
    error."""
    import api.Modules.Billing.Services.webhook as wh
    monkeypatch.setattr(
        wh, "find_store_by_subscription_id",
        MagicMock(return_value=None),
    )
    monkeypatch.setattr(
        wh, "apply_subscription_cancelled", MagicMock(),
    )
    db = MagicMock()
    wh.handle_stripe_event(db, _subscription_deleted_event())
    assert wh.apply_subscription_cancelled.call_count == 0
    assert db.commit.call_count == 0


# ── unhandled event types ──────────────────────────────────


def test_unhandled_event_type_is_noop(monkeypatch):
    """customer.created / invoice.paid / etc. — accepted but not
    acted on. Stripe gets a 200 from the route."""
    import api.Modules.Billing.Services.webhook as wh
    monkeypatch.setattr(wh, "find_store_by_subscription_id", MagicMock())
    monkeypatch.setattr(wh, "apply_subscription_cancelled", MagicMock())
    monkeypatch.setattr(wh, "clear_cancellation_state", MagicMock())
    db = MagicMock()
    wh.handle_stripe_event(
        db, {"type": "invoice.paid", "data": {"object": {}}},
    )
    assert db.commit.call_count == 0
