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
    """Duplicate email is rejected even for second signup attempt."""
    with flask_app.app_context():
        from app import User
        existing = User(username="jane@example.com", full_name="Jane Owner", role="owner", store_id=None)
        existing.set_password("password123")
        db.session.add(existing)
        db.session.commit()
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
    assert b"Create owner account" in rv.data


@pytest.fixture
def owner_client():
    """Client pre-authenticated as an owner with no stores linked."""
    c = flask_app.test_client()
    with flask_app.app_context():
        from app import User
        o = User(username="owner@dashboard.com", full_name="Test Owner", role="owner", store_id=None)
        o.set_password("ownerpass123")
        db.session.add(o)
        db.session.commit()
        oid = o.id
    with c.session_transaction() as sess:
        sess["user_id"] = oid
        sess["role"] = "owner"
        sess["store_id"] = None
    return c


def test_owner_dashboard_loads_no_stores(owner_client):
    rv = owner_client.get("/owner/dashboard")
    assert rv.status_code == 200
    assert b"invite" in rv.data.lower() or b"connect" in rv.data.lower()


def test_owner_dashboard_shows_store_after_link(owner_client):
    with flask_app.app_context():
        from app import User, Store, StoreOwnerLink
        owner = User.query.filter_by(username="owner@dashboard.com").first()
        store = Store.query.filter_by(slug="test-store").first()
        link = StoreOwnerLink(owner_id=owner.id, store_id=store.id)
        db.session.add(link)
        db.session.commit()
    rv = owner_client.get("/owner/dashboard")
    assert rv.status_code == 200
    assert b"Test Store" in rv.data


def test_owner_dashboard_period_filter_today(owner_client):
    rv = owner_client.get("/owner/dashboard?period=today")
    assert rv.status_code == 200


def test_owner_dashboard_period_filter_month(owner_client):
    rv = owner_client.get("/owner/dashboard?period=month")
    assert rv.status_code == 200


def test_owner_dashboard_period_filter_year(owner_client):
    rv = owner_client.get("/owner/dashboard?period=year")
    assert rv.status_code == 200


def test_owner_dashboard_aggregate_counts_transfers(owner_client):
    from datetime import date
    with flask_app.app_context():
        from app import User, Store, StoreOwnerLink, Transfer
        owner = User.query.filter_by(username="owner@dashboard.com").first()
        store = Store.query.filter_by(slug="test-store").first()
        link = StoreOwnerLink(owner_id=owner.id, store_id=store.id)
        db.session.add(link)
        admin = User.query.filter_by(username="admin@test.com").first()
        t = Transfer(store_id=store.id, created_by=admin.id, send_date=date.today(),
                     company="Intermex", sender_name="John", send_amount=100.0)
        db.session.add(t)
        db.session.commit()
    rv = owner_client.get("/owner/dashboard?period=today")
    assert rv.status_code == 200
    assert b"100" in rv.data


@pytest.fixture
def owner_with_store_client():
    """Returns (client, owner_id, store_id) with owner linked to test-store."""
    c = flask_app.test_client()
    with flask_app.app_context():
        from app import User, Store, StoreOwnerLink
        o = User(username="owner2@test.com", full_name="Owner2", role="owner", store_id=None)
        o.set_password("ownerpass123")
        db.session.add(o)
        db.session.flush()
        store = Store.query.filter_by(slug="test-store").first()
        link = StoreOwnerLink(owner_id=o.id, store_id=store.id)
        db.session.add(link)
        db.session.commit()
        oid, sid = o.id, store.id
    with c.session_transaction() as sess:
        sess["user_id"] = oid
        sess["role"] = "owner"
        sess["store_id"] = None
    return c, oid, sid


def _make_valid_invite(store_id, admin_id):
    from app import OwnerInviteCode
    from datetime import datetime, timedelta
    invite = OwnerInviteCode(
        store_id=store_id,
        code="TESTCD01",
        created_by=admin_id,
        expires_at=datetime.utcnow() + timedelta(days=7),
    )
    db.session.add(invite)
    db.session.commit()
    return invite


def test_valid_code_links_owner_to_store(owner_client):
    with flask_app.app_context():
        from app import User, Store
        store = Store.query.filter_by(slug="test-store").first()
        admin = User.query.filter_by(username="admin@test.com").first()
        _make_valid_invite(store.id, admin.id)
    rv = owner_client.post("/owner/link", data={"code": "TESTCD01"})
    assert rv.status_code == 302
    assert "owner/dashboard" in rv.headers["Location"]
    with flask_app.app_context():
        from app import User, StoreOwnerLink, Store
        owner = User.query.filter_by(username="owner@dashboard.com").first()
        store = Store.query.filter_by(slug="test-store").first()
        link = StoreOwnerLink.query.filter_by(owner_id=owner.id, store_id=store.id).first()
        assert link is not None


def test_valid_code_marks_invite_used(owner_client):
    with flask_app.app_context():
        from app import User, Store
        store = Store.query.filter_by(slug="test-store").first()
        admin = User.query.filter_by(username="admin@test.com").first()
        _make_valid_invite(store.id, admin.id)
    owner_client.post("/owner/link", data={"code": "TESTCD01"})
    with flask_app.app_context():
        from app import OwnerInviteCode
        invite = OwnerInviteCode.query.filter_by(code="TESTCD01").first()
        assert invite.used_at is not None


def test_expired_code_rejected(owner_client):
    with flask_app.app_context():
        from app import User, Store, OwnerInviteCode
        from datetime import datetime, timedelta
        store = Store.query.filter_by(slug="test-store").first()
        admin = User.query.filter_by(username="admin@test.com").first()
        invite = OwnerInviteCode(
            store_id=store.id, code="EXPIRED1", created_by=admin.id,
            expires_at=datetime.utcnow() - timedelta(days=1),
        )
        db.session.add(invite)
        db.session.commit()
    rv = owner_client.post("/owner/link", data={"code": "EXPIRED1"}, follow_redirects=True)
    assert b"expired" in rv.data.lower() or b"invalid" in rv.data.lower()


def test_used_code_rejected(owner_client):
    with flask_app.app_context():
        from app import User, Store, OwnerInviteCode
        from datetime import datetime, timedelta
        store = Store.query.filter_by(slug="test-store").first()
        admin = User.query.filter_by(username="admin@test.com").first()
        invite = OwnerInviteCode(
            store_id=store.id, code="USED0001", created_by=admin.id,
            expires_at=datetime.utcnow() + timedelta(days=7),
            used_at=datetime.utcnow(),
        )
        db.session.add(invite)
        db.session.commit()
    rv = owner_client.post("/owner/link", data={"code": "USED0001"}, follow_redirects=True)
    assert b"expired" in rv.data.lower() or b"invalid" in rv.data.lower()


def test_invalid_code_rejected(owner_client):
    rv = owner_client.post("/owner/link", data={"code": "BADCODE1"}, follow_redirects=True)
    assert b"invalid" in rv.data.lower() or b"expired" in rv.data.lower()


def test_already_linked_handled_gracefully(owner_client):
    with flask_app.app_context():
        from app import User, Store, StoreOwnerLink, OwnerInviteCode
        from datetime import datetime, timedelta
        store = Store.query.filter_by(slug="test-store").first()
        admin = User.query.filter_by(username="admin@test.com").first()
        owner = User.query.filter_by(username="owner@dashboard.com").first()
        existing = StoreOwnerLink(owner_id=owner.id, store_id=store.id)
        db.session.add(existing)
        invite = OwnerInviteCode(
            store_id=store.id, code="LINKDUP1", created_by=admin.id,
            expires_at=datetime.utcnow() + timedelta(days=7),
        )
        db.session.add(invite)
        db.session.commit()
    rv = owner_client.post("/owner/link", data={"code": "LINKDUP1"}, follow_redirects=True)
    assert rv.status_code == 200
    assert b"already connected" in rv.data.lower()
    with flask_app.app_context():
        from app import OwnerInviteCode
        invite = OwnerInviteCode.query.filter_by(code="LINKDUP1").first()
        assert invite.used_at is None, "invite should not be consumed when owner is already linked"


def test_owner_can_unlink_store(owner_with_store_client):
    c, oid, sid = owner_with_store_client
    rv = c.post(f"/owner/unlink/{sid}")
    assert rv.status_code == 302
    with flask_app.app_context():
        from app import StoreOwnerLink
        link = StoreOwnerLink.query.filter_by(owner_id=oid, store_id=sid).first()
        assert link is None


def test_unlink_nonexistent_returns_404(owner_client):
    rv = owner_client.post("/owner/unlink/99999")
    assert rv.status_code == 404


def test_admin_generate_owner_code(logged_in_client):
    rv = logged_in_client.post("/admin/settings/owner/generate-code")
    assert rv.status_code == 302
    with flask_app.app_context():
        from app import Store, OwnerInviteCode
        store = Store.query.filter_by(slug="test-store").first()
        code = OwnerInviteCode.query.filter_by(store_id=store.id).first()
        assert code is not None
        assert len(code.code) == 8
        assert code.code == code.code.upper()
        assert code.used_at is None


def test_generate_code_invalidates_previous(logged_in_client):
    logged_in_client.post("/admin/settings/owner/generate-code")
    logged_in_client.post("/admin/settings/owner/generate-code")
    with flask_app.app_context():
        from app import Store, OwnerInviteCode
        from datetime import datetime
        store = Store.query.filter_by(slug="test-store").first()
        active = OwnerInviteCode.query.filter(
            OwnerInviteCode.store_id == store.id,
            OwnerInviteCode.used_at.is_(None),
            OwnerInviteCode.expires_at > datetime.utcnow()
        ).all()
        assert len(active) == 1


def test_code_has_7_day_expiry(logged_in_client):
    from datetime import datetime, timedelta
    logged_in_client.post("/admin/settings/owner/generate-code")
    with flask_app.app_context():
        from app import Store, OwnerInviteCode
        store = Store.query.filter_by(slug="test-store").first()
        code = OwnerInviteCode.query.filter_by(store_id=store.id).order_by(OwnerInviteCode.created_at.desc()).first()
        delta = code.expires_at - code.created_at
        assert 6 <= delta.days <= 7


def test_admin_owner_access_tab_shows_no_code_state(logged_in_client):
    rv = logged_in_client.get("/admin/settings?tab=owner")
    assert rv.status_code == 200
    assert b"Generate" in rv.data or b"generate" in rv.data


def test_admin_owner_access_tab_shows_active_code(logged_in_client):
    logged_in_client.post("/admin/settings/owner/generate-code")
    rv = logged_in_client.get("/admin/settings?tab=owner")
    assert rv.status_code == 200


def test_admin_remove_owner_access(logged_in_client):
    with flask_app.app_context():
        from app import User, Store, StoreOwnerLink
        store = Store.query.filter_by(slug="test-store").first()
        o = User(username="owner3@test.com", full_name="Owner3", role="owner", store_id=None)
        o.set_password("ownerpass123")
        db.session.add(o)
        db.session.flush()
        link = StoreOwnerLink(owner_id=o.id, store_id=store.id)
        db.session.add(link)
        db.session.commit()
        oid = o.id
    rv = logged_in_client.post("/admin/settings/owner/remove-access", data={"owner_id": oid})
    assert rv.status_code == 302
    with flask_app.app_context():
        from app import Store, StoreOwnerLink
        store = Store.query.filter_by(slug="test-store").first()
        link = StoreOwnerLink.query.filter_by(store_id=store.id, owner_id=oid).first()
        assert link is None
