import pytest
from app import app as flask_app, db


def test_store_owner_link_model_exists():
    with flask_app.app_context():
        from app import StoreOwnerLink
        assert hasattr(StoreOwnerLink, "owner_id")
        assert hasattr(StoreOwnerLink, "store_id")
        assert hasattr(StoreOwnerLink, "linked_at")


def test_owner_invite_code_model_exists():
    with flask_app.app_context():
        from app import OwnerInviteCode
        assert hasattr(OwnerInviteCode, "store_id")
        assert hasattr(OwnerInviteCode, "code")
        assert hasattr(OwnerInviteCode, "created_by")
        assert hasattr(OwnerInviteCode, "expires_at")
        assert hasattr(OwnerInviteCode, "used_at")
        assert hasattr(OwnerInviteCode, "used_by_owner_id")


def test_store_owner_link_unique_constraint():
    with flask_app.app_context():
        from app import StoreOwnerLink, User, Store
        store = Store.query.filter_by(slug="test-store").first()
        assert store is not None, "conftest must seed a store with slug='test-store'"
        owner = User(username="owner@test.com", full_name="Owner", role="owner", store_id=None)
        owner.set_password("pass1234!")
        db.session.add(owner)
        db.session.flush()
        link1 = StoreOwnerLink(owner_id=owner.id, store_id=store.id)
        link2 = StoreOwnerLink(owner_id=owner.id, store_id=store.id)
        db.session.add(link1)
        db.session.flush()
        db.session.add(link2)
        with pytest.raises(Exception):
            db.session.flush()
        db.session.rollback()


def test_owner_required_blocks_non_owner(client):
    """Non-owner users get 403 from owner-only routes."""
    with flask_app.app_context():
        from app import User
        u = User.query.filter_by(username="admin@test.com").first()
        uid, sid = u.id, u.store_id
    with client.session_transaction() as sess:
        sess["user_id"] = uid
        sess["role"] = "admin"
        sess["store_id"] = sid
    rv = client.get("/owner/dashboard")
    assert rv.status_code == 403


def test_owner_required_blocks_unauthenticated(client):
    rv = client.get("/owner/dashboard")
    assert rv.status_code == 302
    assert "/login" in rv.headers["Location"]


def test_login_redirects_owner_to_owner_dashboard(client):
    with flask_app.app_context():
        from app import User
        o = User(username="owner@test.com", full_name="Test Owner", role="owner", store_id=None)
        o.set_password("ownerpass123")
        db.session.add(o)
        db.session.commit()
    rv = client.post("/login", data={"username": "owner@test.com", "password": "ownerpass123"})
    assert rv.status_code == 302
    assert "owner/dashboard" in rv.headers["Location"]


def test_login_already_logged_in_owner_redirects_to_owner_dashboard(client):
    """Owner already in session hitting /login should go to owner_dashboard."""
    with flask_app.app_context():
        from app import User
        o = User(username="owner_loggedin@test.com", full_name="Owner", role="owner", store_id=None)
        o.set_password("ownerpass123")
        db.session.add(o)
        db.session.commit()
        oid = o.id
    with client.session_transaction() as sess:
        sess["user_id"] = oid
        sess["role"] = "owner"
        sess["store_id"] = None
    rv = client.get("/login")
    assert rv.status_code == 302
    assert "owner/dashboard" in rv.headers["Location"]
