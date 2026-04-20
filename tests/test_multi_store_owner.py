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


def test_owner_signup_success(client):
    rv = client.post("/signup/owner", data={
        "full_name": "Jane Owner",
        "email": "jane@example.com",
        "password": "password123",
    })
    assert rv.status_code == 302
    assert "owner/dashboard" in rv.headers["Location"]
    with flask_app.app_context():
        from app import User
        u = User.query.filter_by(username="jane@example.com", store_id=None).first()
        assert u is not None
        assert u.role == "owner"
        assert u.store_id is None
        assert u.full_name == "Jane Owner"


def test_owner_signup_sets_session(client):
    rv = client.post("/signup/owner", data={
        "full_name": "Jane Owner",
        "email": "jane@example.com",
        "password": "password123",
    })
    with client.session_transaction() as sess:
        assert sess["role"] == "owner"
        assert sess.get("store_id") is None


def test_owner_signup_duplicate_email_rejected(client):
    client.post("/signup/owner", data={
        "full_name": "Jane Owner", "email": "jane@example.com", "password": "password123",
    })
    rv = client.post("/signup/owner", data={
        "full_name": "Jane 2", "email": "jane@example.com", "password": "password123",
    })
    assert rv.status_code == 200
    assert b"already exists" in rv.data


def test_owner_signup_short_password_rejected(client):
    rv = client.post("/signup/owner", data={
        "full_name": "Jane Owner", "email": "jane@example.com", "password": "short",
    })
    assert rv.status_code == 200
    assert b"8 characters" in rv.data


def test_owner_signup_invalid_email_rejected(client):
    rv = client.post("/signup/owner", data={
        "full_name": "Jane Owner", "email": "notanemail", "password": "password123",
    })
    assert rv.status_code == 200
    assert b"valid email" in rv.data


def test_owner_signup_blocks_admin_email(client):
    """Existing store admin email cannot be reused as an owner."""
    rv = client.post("/signup/owner", data={
        "full_name": "Jane Owner", "email": "admin@test.com", "password": "password123",
    })
    assert rv.status_code == 200
    assert b"already exists" in rv.data


def test_owner_signup_get_renders_form(client):
    rv = client.get("/signup/owner")
    assert rv.status_code == 200
    assert b"owner" in rv.data.lower()
