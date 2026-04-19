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

def test_trial_set_but_no_grace_date():
    from app import get_trial_status
    # grace_ends_at=None should not crash
    s = _store(plan="trial",
               trial_ends_at=datetime.utcnow() + timedelta(days=7),
               grace_ends_at=None)
    assert get_trial_status(s) == "active"


def test_expired_store_redirected_to_subscribe(client):
    from app import db, Store, User
    with client.application.app_context():
        s = Store(name="Expired Co", slug="expired-co",
                  email="expired@test.com", plan="trial",
                  trial_ends_at=datetime.utcnow() - timedelta(days=5),
                  grace_ends_at=datetime.utcnow() - timedelta(days=1))
        db.session.add(s)
        db.session.flush()
        u = User(store_id=s.id, username="expired@test.com",
                 full_name="Expired Admin", role="admin")
        u.set_password("testpass123!")
        db.session.add(u)
        db.session.commit()
        uid, sid = u.id, s.id

    with client.session_transaction() as sess:
        sess["user_id"] = uid
        sess["role"] = "admin"
        sess["store_id"] = sid

    resp = client.get("/dashboard", follow_redirects=False)
    assert resp.status_code == 302
    assert "/subscribe" in resp.headers["Location"]


def test_active_trial_reaches_dashboard(logged_in_client):
    resp = logged_in_client.get("/dashboard")
    assert resp.status_code == 200


def test_subscribe_is_accessible_when_expired(client):
    """Expired stores must be able to reach /subscribe (not infinite redirect)."""
    from app import db, Store, User
    with client.application.app_context():
        s = Store(name="Exp2 Co", slug="exp2-co",
                  email="exp2@test.com", plan="trial",
                  trial_ends_at=datetime.utcnow() - timedelta(days=5),
                  grace_ends_at=datetime.utcnow() - timedelta(days=1))
        db.session.add(s)
        db.session.flush()
        u = User(store_id=s.id, username="exp2@test.com",
                 full_name="Exp2 Admin", role="admin")
        u.set_password("testpass123!")
        db.session.add(u)
        db.session.commit()
        uid, sid = u.id, s.id

    with client.session_transaction() as sess:
        sess["user_id"] = uid
        sess["role"] = "admin"
        sess["store_id"] = sid

    resp = client.get("/subscribe")
    assert resp.status_code == 200
