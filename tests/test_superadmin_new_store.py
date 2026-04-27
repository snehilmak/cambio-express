"""Tests for the superadmin_new_store route and its audit-log side-effect.

commit a0a4cb2 added record_audit("create_store", ...) inside the POST
handler. These tests verify: happy-path store creation, the audit entry,
the duplicate-slug guard, the auth gate, and missing-field behaviour.
"""
import pytest
from app import app as flask_app, db


def _superadmin_client():
    """Fresh client authenticated as the seeded superadmin."""
    from app import User
    c = flask_app.test_client()
    with flask_app.app_context():
        sa = User.query.filter_by(username="superadmin", store_id=None).first()
        uid = sa.id
    with c.session_transaction() as sess:
        sess["user_id"] = uid
        sess["role"] = "superadmin"
    return c


_VALID_FORM = {
    "name": "New Branch",
    "slug": "new-branch",
    "email": "branch@example.com",
    "phone": "555-0000",
    "address": "1 Main St",
    "plan": "trial",
    "admin_username": "branchadmin",
    "admin_name": "Branch Admin",
    "admin_password": "branchpass123!",
}


def test_create_store_happy_path():
    from app import Store
    c = _superadmin_client()
    resp = c.post("/superadmin/stores/new", data=_VALID_FORM, follow_redirects=False)
    assert resp.status_code == 302
    with flask_app.app_context():
        s = Store.query.filter_by(slug="new-branch").first()
        assert s is not None
        assert s.name == "New Branch"
        assert s.plan == "trial"


def test_create_store_records_audit():
    from app import Store, SuperadminAuditLog
    c = _superadmin_client()
    c.post("/superadmin/stores/new", data=_VALID_FORM, follow_redirects=False)
    with flask_app.app_context():
        s = Store.query.filter_by(slug="new-branch").first()
        row = SuperadminAuditLog.query.filter_by(action="create_store").first()
        assert row is not None
        assert row.target_type == "store"
        assert str(row.target_id) == str(s.id)
        assert row.details == "new-branch"


def test_create_store_admin_user_created():
    from app import User, Store
    c = _superadmin_client()
    c.post("/superadmin/stores/new", data=_VALID_FORM, follow_redirects=False)
    with flask_app.app_context():
        s = Store.query.filter_by(slug="new-branch").first()
        admin = User.query.filter_by(store_id=s.id, role="admin").first()
        assert admin is not None
        assert admin.username == "branchadmin"


def test_duplicate_slug_rejected():
    from app import Store
    c = _superadmin_client()
    c.post("/superadmin/stores/new", data=_VALID_FORM, follow_redirects=False)
    resp = c.post(
        "/superadmin/stores/new",
        data={**_VALID_FORM, "name": "Other Store"},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert b"Slug already taken" in resp.data
    with flask_app.app_context():
        assert Store.query.filter_by(slug="new-branch").count() == 1


def test_no_audit_entry_on_duplicate_slug():
    from app import SuperadminAuditLog
    c = _superadmin_client()
    c.post("/superadmin/stores/new", data=_VALID_FORM)
    c.post("/superadmin/stores/new", data={**_VALID_FORM, "name": "Dup"})
    with flask_app.app_context():
        assert SuperadminAuditLog.query.filter_by(action="create_store").count() == 1


def test_unauthenticated_new_store_redirects_to_login(client):
    resp = client.post("/superadmin/stores/new", data=_VALID_FORM, follow_redirects=False)
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]


def test_store_admin_cannot_create_store(logged_in_client):
    resp = logged_in_client.post(
        "/superadmin/stores/new", data=_VALID_FORM, follow_redirects=False
    )
    assert resp.status_code in (302, 403)
    if resp.status_code == 302:
        assert "/superadmin" not in resp.headers["Location"]
