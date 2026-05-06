"""Unit tests for Billing.Services.store_state (PR 48)."""
from datetime import datetime, timedelta
from unittest.mock import MagicMock


def _store(*, plan="trial", addons=None, data_retention_until=None):
    """Stand-in store with only the fields the helpers read."""
    s = MagicMock()
    s.plan = plan
    s.addons = addons
    s.data_retention_until = data_retention_until
    return s


# ── store_addon_keys ────────────────────────────────────────


def test_store_addon_keys_returns_empty_for_none():
    from api.Modules.Billing.Services import store_addon_keys
    assert store_addon_keys(None) == set()


def test_store_addon_keys_returns_empty_for_blank_addons():
    from api.Modules.Billing.Services import store_addon_keys
    assert store_addon_keys(_store(addons=None)) == set()
    assert store_addon_keys(_store(addons="")) == set()


def test_store_addon_keys_parses_csv():
    from api.Modules.Billing.Services import store_addon_keys
    assert store_addon_keys(_store(addons="tv_display")) == {"tv_display"}
    assert store_addon_keys(_store(addons="tv_display,bank_sync")) == {
        "tv_display", "bank_sync",
    }


def test_store_addon_keys_strips_whitespace():
    from api.Modules.Billing.Services import store_addon_keys
    assert store_addon_keys(_store(addons="  tv_display ,  bank_sync  ")) == {
        "tv_display", "bank_sync",
    }


def test_store_addon_keys_drops_empty_entries():
    """Trailing commas / double commas don't produce empty-string keys."""
    from api.Modules.Billing.Services import store_addon_keys
    assert store_addon_keys(_store(addons="tv_display,,bank_sync,")) == {
        "tv_display", "bank_sync",
    }


# ── store_has_paid_plan ─────────────────────────────────────


def test_store_has_paid_plan_basic_pro_true():
    from api.Modules.Billing.Services import store_has_paid_plan
    assert store_has_paid_plan(_store(plan="basic")) is True
    assert store_has_paid_plan(_store(plan="pro")) is True


def test_store_has_paid_plan_trial_inactive_false():
    from api.Modules.Billing.Services import store_has_paid_plan
    assert store_has_paid_plan(_store(plan="trial")) is False
    assert store_has_paid_plan(_store(plan="inactive")) is False


def test_store_has_paid_plan_none_false():
    from api.Modules.Billing.Services import store_has_paid_plan
    assert store_has_paid_plan(None) is False


def test_store_has_paid_plan_unknown_plan_false():
    from api.Modules.Billing.Services import store_has_paid_plan
    assert store_has_paid_plan(_store(plan="garbage")) is False


# ── data_retention_days_left ────────────────────────────────


def test_data_retention_days_left_none_for_no_timer():
    from api.Modules.Billing.Services import data_retention_days_left
    assert data_retention_days_left(_store(data_retention_until=None)) is None
    assert data_retention_days_left(None) is None


def test_data_retention_days_left_future_returns_days():
    from api.Modules.Billing.Services import data_retention_days_left
    s = _store(
        data_retention_until=datetime.utcnow() + timedelta(days=30),
    )
    days = data_retention_days_left(s)
    # Allow ±1 for clock skew during the test
    assert 29 <= days <= 30


def test_data_retention_days_left_past_returns_zero():
    """Already-elapsed timer reports 0 (purge cron will catch on
    next run). Don't return negative — chrome shows
    'Cancelled, data purges in N days' and N must be ≥ 0."""
    from api.Modules.Billing.Services import data_retention_days_left
    s = _store(
        data_retention_until=datetime.utcnow() - timedelta(days=5),
    )
    assert data_retention_days_left(s) == 0
