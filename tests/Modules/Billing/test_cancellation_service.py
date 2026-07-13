"""Unit tests for Billing.Services.cancellation (PR 46)."""
from datetime import datetime, timedelta
from unittest.mock import MagicMock
from tests._app import db, db_session


def _store(*, sub_id="sub_xyz", plan="basic", billing_cycle="monthly"):
    """Mock store object with the fields the Service reads/writes."""
    s = MagicMock()
    s.id = 99
    s.stripe_subscription_id = sub_id
    s.plan = plan
    s.billing_cycle = billing_cycle
    s.canceled_at = None
    s.data_retention_until = None
    s.trial_reminder_sent_at = None
    return s


# ── find_store_by_subscription_id ───────────────────────────


def test_find_store_returns_match(test_store_id):
    from api.Modules.Tenancy.Models import Store
    from tests._app import db
    from api.Modules.Billing.Services import find_store_by_subscription_id
    with db_session():
        s = db.session.get(Store,test_store_id)
        s.stripe_subscription_id = "sub_test123"
        db.session.commit()
        out = find_store_by_subscription_id(db.session, "sub_test123")
        assert out is not None
        assert out.id == test_store_id


def test_find_store_returns_none_for_unknown():
    from tests._app import db
    from api.Modules.Billing.Services import find_store_by_subscription_id
    with db_session():
        assert find_store_by_subscription_id(
            db.session, "sub_nope",
        ) is None


def test_find_store_returns_none_for_empty():
    """Empty subscription_id short-circuits before the DB hit."""
    from tests._app import db
    from api.Modules.Billing.Services import find_store_by_subscription_id
    with db_session():
        assert find_store_by_subscription_id(db.session, "") is None
        assert find_store_by_subscription_id(db.session, None) is None


# ── apply_subscription_cancelled ────────────────────────────


def test_apply_cancellation_sets_inactive_state():
    from api.Modules.Billing.Services import apply_subscription_cancelled
    s = _store()
    apply_subscription_cancelled(s)
    assert s.plan == "inactive"
    assert s.billing_cycle == ""
    assert s.stripe_subscription_id == ""
    assert s.canceled_at is not None
    assert s.data_retention_until is not None
    # Default retention = 180 days
    delta = s.data_retention_until - s.canceled_at
    assert delta == timedelta(days=180)


def test_apply_cancellation_respects_custom_retention():
    from api.Modules.Billing.Services import apply_subscription_cancelled
    s = _store()
    apply_subscription_cancelled(s, retention_days=90)
    delta = s.data_retention_until - s.canceled_at
    assert delta == timedelta(days=90)


def test_apply_cancellation_does_not_restamp_on_redelivery():
    """A duplicate `customer.subscription.deleted` (Stripe retries
    aggressively) must NOT push the retention clock forward — the
    180-day window counts from the FIRST cancellation. Otherwise a
    store cancelled 170 days ago gets a fresh window on every retry
    and the purge never catches it."""
    from api.Modules.Billing.Services import apply_subscription_cancelled
    s = _store()
    apply_subscription_cancelled(s)
    first_canceled = s.canceled_at
    first_retention = s.data_retention_until
    # Simulate a duplicate webhook delivery.
    apply_subscription_cancelled(s)
    assert s.canceled_at == first_canceled
    assert s.data_retention_until == first_retention
    # Terminal state fields stay correct.
    assert s.plan == "inactive"
    assert s.stripe_subscription_id == ""


def test_re_cancel_after_resubscribe_stamps_fresh_window():
    """A returning customer clears the clock (clear_cancellation_
    state sets data_retention_until=None); a later re-cancel must
    then stamp a fresh window rather than no-op."""
    from api.Modules.Billing.Services import (
        apply_subscription_cancelled, clear_cancellation_state,
    )
    s = _store()
    apply_subscription_cancelled(s)
    # Customer comes back.
    s.plan = "basic"
    clear_cancellation_state(s)
    assert s.data_retention_until is None
    # ...then cancels again — fresh window stamped.
    apply_subscription_cancelled(s)
    assert s.data_retention_until is not None
    assert s.data_retention_until - s.canceled_at == timedelta(days=180)


# ── clear_cancellation_state ────────────────────────────────


def test_clear_cancellation_state_resets_all_three_fields():
    from api.Modules.Billing.Services import clear_cancellation_state
    s = _store()
    s.canceled_at = datetime(2025, 1, 1)
    s.data_retention_until = datetime(2025, 7, 1)
    s.trial_reminder_sent_at = datetime(2025, 1, 5)
    clear_cancellation_state(s)
    assert s.canceled_at is None
    assert s.data_retention_until is None
    assert s.trial_reminder_sent_at is None


def test_clear_cancellation_state_safe_when_already_clean():
    """All-None going in stays all-None (no-op)."""
    from api.Modules.Billing.Services import clear_cancellation_state
    s = _store()
    s.canceled_at = None
    s.data_retention_until = None
    s.trial_reminder_sent_at = None
    clear_cancellation_state(s)
    assert s.canceled_at is None
    assert s.data_retention_until is None
    assert s.trial_reminder_sent_at is None
