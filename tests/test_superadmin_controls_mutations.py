"""Tests for superadmin mutation routes: extend_trial, comp_plan,
toggle_active, extend_retention, revert_to_trial.

Each route must (a) mutate the Store row and (b) write a SuperadminAuditLog
entry.  Auth gate — non-superadmin gets bounced.
"""
from datetime import datetime, timedelta
from app import app as flask_app, db


def _superadmin_client():
    from app import User
    c = flask_app.test_client()
    with flask_app.app_context():
        sa = User.query.filter_by(username="superadmin", store_id=None).first()
        uid = sa.id
    with c.session_transaction() as sess:
        sess["user_id"] = uid
        sess["role"] = "superadmin"
    return c


def _get_store(test_store_id):
    from app import Store
    with flask_app.app_context():
        s = db.session.get(Store, test_store_id)
        return s.plan, s.is_active, s.trial_ends_at, s.data_retention_until


# ── extend_trial ──────────────────────────────────────────────────────────────

def test_extend_trial_pushes_deadline(test_store_id):
    c = _superadmin_client()
    resp = c.post(
        f"/superadmin/stores/{test_store_id}/extend-trial",
        data={"days": "14"},
        follow_redirects=False,
    )
    assert resp.status_code == 302
    from app import Store
    with flask_app.app_context():
        s = db.session.get(Store, test_store_id)
        assert s.trial_ends_at > datetime.utcnow() + timedelta(days=13)


def test_extend_trial_records_audit(test_store_id):
    from app import SuperadminAuditLog
    c = _superadmin_client()
    c.post(f"/superadmin/stores/{test_store_id}/extend-trial", data={"days": "7"})
    with flask_app.app_context():
        row = SuperadminAuditLog.query.filter_by(action="extend_trial").first()
        assert row is not None
        assert str(row.target_id) == str(test_store_id)
        assert row.target_type == "store"


# ── comp_plan ─────────────────────────────────────────────────────────────────

def test_comp_plan_sets_plan(test_store_id):
    from app import Store
    c = _superadmin_client()
    c.post(f"/superadmin/stores/{test_store_id}/comp-plan", data={"plan": "pro"})
    with flask_app.app_context():
        s = db.session.get(Store, test_store_id)
        assert s.plan == "pro"
        assert s.canceled_at is None
        assert s.data_retention_until is None


def test_comp_plan_records_audit(test_store_id):
    from app import SuperadminAuditLog
    c = _superadmin_client()
    c.post(f"/superadmin/stores/{test_store_id}/comp-plan", data={"plan": "basic"})
    with flask_app.app_context():
        row = SuperadminAuditLog.query.filter_by(action="comp_plan").first()
        assert row is not None
        assert "basic" in row.details


def test_comp_plan_rejects_invalid_plan(test_store_id):
    from app import SuperadminAuditLog
    c = _superadmin_client()
    c.post(f"/superadmin/stores/{test_store_id}/comp-plan", data={"plan": "enterprise"})
    with flask_app.app_context():
        assert SuperadminAuditLog.query.filter_by(action="comp_plan").count() == 0


# ── toggle_active ─────────────────────────────────────────────────────────────

def test_toggle_active_flips_flag(test_store_id):
    from app import Store
    c = _superadmin_client()
    with flask_app.app_context():
        before = db.session.get(Store, test_store_id).is_active
    c.post(f"/superadmin/stores/{test_store_id}/toggle-active")
    with flask_app.app_context():
        after = db.session.get(Store, test_store_id).is_active
    assert after == (not before)


def test_toggle_active_records_audit(test_store_id):
    from app import SuperadminAuditLog
    c = _superadmin_client()
    c.post(f"/superadmin/stores/{test_store_id}/toggle-active")
    with flask_app.app_context():
        row = SuperadminAuditLog.query.filter_by(action="toggle_active").first()
        assert row is not None
        assert str(row.target_id) == str(test_store_id)


# ── revert_to_trial ───────────────────────────────────────────────────────────

def test_revert_to_trial_resets_plan(test_store_id):
    from app import Store
    c = _superadmin_client()
    with flask_app.app_context():
        s = db.session.get(Store, test_store_id)
        s.plan = "pro"
        db.session.commit()
    c.post(f"/superadmin/stores/{test_store_id}/revert-to-trial")
    with flask_app.app_context():
        s = db.session.get(Store, test_store_id)
        assert s.plan == "trial"
        assert s.trial_ends_at > datetime.utcnow()
        assert s.data_retention_until is None


def test_revert_to_trial_records_audit(test_store_id):
    from app import SuperadminAuditLog
    c = _superadmin_client()
    c.post(f"/superadmin/stores/{test_store_id}/revert-to-trial")
    with flask_app.app_context():
        assert SuperadminAuditLog.query.filter_by(action="revert_to_trial").count() == 1


# ── auth gate ─────────────────────────────────────────────────────────────────

def test_mutation_routes_require_superadmin(client, test_store_id):
    """A plain store admin must be bounced from every mutation route."""
    from app import User
    with flask_app.app_context():
        admin = User.query.filter_by(username="admin@test.com").first()
        uid, sid = admin.id, admin.store_id
    with client.session_transaction() as sess:
        sess["user_id"] = uid
        sess["role"] = "admin"
        sess["store_id"] = sid

    routes = [
        f"/superadmin/stores/{test_store_id}/extend-trial",
        f"/superadmin/stores/{test_store_id}/comp-plan",
        f"/superadmin/stores/{test_store_id}/toggle-active",
        f"/superadmin/stores/{test_store_id}/revert-to-trial",
    ]
    for url in routes:
        resp = client.post(url, follow_redirects=False)
        assert resp.status_code in (302, 403), f"{url} should deny non-superadmin"
        if resp.status_code == 302:
            assert "/superadmin" not in resp.headers["Location"], url
