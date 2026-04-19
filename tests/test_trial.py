from datetime import datetime, timedelta


def _store(plan="trial", trial_ends_at=None, grace_ends_at=None):
    class S:
        pass
    s = S()
    s.plan = plan
    s.trial_ends_at = trial_ends_at
    s.grace_ends_at = grace_ends_at
    return s


def test_none_store_is_exempt():
    from app import get_trial_status
    assert get_trial_status(None) == "exempt"

def test_no_trial_dates_is_exempt():
    from app import get_trial_status
    assert get_trial_status(_store(plan="trial", trial_ends_at=None)) == "exempt"

def test_basic_plan_is_exempt():
    from app import get_trial_status
    assert get_trial_status(_store(plan="basic",
        trial_ends_at=datetime.utcnow() - timedelta(days=1),
        grace_ends_at=datetime.utcnow() + timedelta(days=3))) == "exempt"

def test_pro_plan_is_exempt():
    from app import get_trial_status
    assert get_trial_status(_store(plan="pro",
        trial_ends_at=datetime.utcnow() - timedelta(days=1),
        grace_ends_at=datetime.utcnow() + timedelta(days=3))) == "exempt"

def test_inactive_plan_is_expired():
    from app import get_trial_status
    assert get_trial_status(_store(plan="inactive")) == "expired"

def test_active_trial_with_days_remaining():
    from app import get_trial_status
    s = _store(plan="trial",
               trial_ends_at=datetime.utcnow() + timedelta(days=7),
               grace_ends_at=datetime.utcnow() + timedelta(days=11))
    assert get_trial_status(s) == "active"

def test_expiring_soon_within_3_days():
    from app import get_trial_status
    s = _store(plan="trial",
               trial_ends_at=datetime.utcnow() + timedelta(hours=36),
               grace_ends_at=datetime.utcnow() + timedelta(days=4))
    assert get_trial_status(s) == "expiring_soon"

def test_grace_after_trial_end():
    from app import get_trial_status
    s = _store(plan="trial",
               trial_ends_at=datetime.utcnow() - timedelta(hours=12),
               grace_ends_at=datetime.utcnow() + timedelta(days=3))
    assert get_trial_status(s) == "grace"

def test_expired_after_grace_end():
    from app import get_trial_status
    s = _store(plan="trial",
               trial_ends_at=datetime.utcnow() - timedelta(days=5),
               grace_ends_at=datetime.utcnow() - timedelta(days=1))
    assert get_trial_status(s) == "expired"
