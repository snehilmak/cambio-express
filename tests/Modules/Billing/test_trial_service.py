"""Unit tests for Billing.Services.trial (PR 47)."""
from datetime import datetime, timedelta
from unittest.mock import MagicMock


def _store(*, plan="trial", trial_ends_at=None, grace_ends_at=None):
    """Stand-in store for the get_trial_status purity tests."""
    s = MagicMock()
    s.plan = plan
    s.trial_ends_at = trial_ends_at
    s.grace_ends_at = grace_ends_at
    return s


# ── get_trial_status ────────────────────────────────────────


def test_none_store_is_exempt():
    """Logged-out / superadmin contexts pass None; the chrome
    treats that as "no trial banner shown"."""
    from api.Modules.Billing.Services import get_trial_status
    assert get_trial_status(None) == "exempt"


def test_basic_plan_is_exempt():
    from api.Modules.Billing.Services import get_trial_status
    assert get_trial_status(_store(plan="basic")) == "exempt"


def test_pro_plan_is_exempt():
    from api.Modules.Billing.Services import get_trial_status
    assert get_trial_status(_store(plan="pro")) == "exempt"


def test_inactive_plan_is_expired():
    """Cancelled stores read as expired regardless of timestamps."""
    from api.Modules.Billing.Services import get_trial_status
    assert get_trial_status(_store(plan="inactive")) == "expired"


def test_trial_with_no_end_date_is_exempt():
    """Legacy rows that never had a trial timestamp set."""
    from api.Modules.Billing.Services import get_trial_status
    assert get_trial_status(_store(trial_ends_at=None)) == "exempt"


def test_active_trial_with_lots_of_time():
    from api.Modules.Billing.Services import get_trial_status
    s = _store(
        trial_ends_at=datetime.utcnow() + timedelta(days=5),
        grace_ends_at=datetime.utcnow() + timedelta(days=9),
    )
    assert get_trial_status(s) == "active"


def test_expiring_soon_when_within_threshold():
    """≤ 3 days remaining → 'expiring_soon' (legacy threshold)."""
    from api.Modules.Billing.Services import get_trial_status
    s = _store(
        trial_ends_at=datetime.utcnow() + timedelta(days=2),
        grace_ends_at=datetime.utcnow() + timedelta(days=6),
    )
    assert get_trial_status(s) == "expiring_soon"


def test_grace_after_trial_ends_but_before_grace_ends():
    from api.Modules.Billing.Services import get_trial_status
    s = _store(
        trial_ends_at=datetime.utcnow() - timedelta(days=1),
        grace_ends_at=datetime.utcnow() + timedelta(days=2),
    )
    assert get_trial_status(s) == "grace"


def test_expired_when_grace_window_elapsed():
    from api.Modules.Billing.Services import get_trial_status
    s = _store(
        trial_ends_at=datetime.utcnow() - timedelta(days=10),
        grace_ends_at=datetime.utcnow() - timedelta(days=2),
    )
    assert get_trial_status(s) == "expired"


def test_grace_when_no_grace_end_set():
    """If grace_ends_at is None, only trial_ends_at gates the
    "grace" → "expired" transition (defensive against legacy rows
    that never got a grace window)."""
    from api.Modules.Billing.Services import get_trial_status
    s = _store(
        trial_ends_at=datetime.utcnow() - timedelta(days=1),
        grace_ends_at=None,
    )
    # Past trial_ends_at + no grace cap → "grace"
    assert get_trial_status(s) == "grace"


def test_threshold_constant_exposed():
    """Tests + future external callers can read the threshold from
    the module rather than hard-coding 3."""
    from api.Modules.Billing.Services import EXPIRING_SOON_THRESHOLD_DAYS
    assert EXPIRING_SOON_THRESHOLD_DAYS == 3


def test_legacy_app_helper_delegates():
    """Smoke test the Flask wrapper still returns the same value."""
    from app import get_trial_status as legacy_get_trial_status
    assert legacy_get_trial_status(None) == "exempt"
    s = _store(plan="basic")
    assert legacy_get_trial_status(s) == "exempt"
