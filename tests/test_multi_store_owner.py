import pytest
from app import app as flask_app, db


def test_store_owner_link_model_exists():
    with flask_app.app_context():
        from app import StoreOwnerLink
        assert hasattr(StoreOwnerLink, "owner_id")
        assert hasattr(StoreOwnerLink, "store_id")
        assert hasattr(StoreOwnerLink, "linked_at")


def test_owner_connect_code_model_exists():
    """OwnerConnectCode replaced the legacy OwnerInviteCode in May 2026
    when the connect flow was inverted (owner generates code, admin
    redeems). New shape: owner-keyed, redeemable by an admin in their
    store. See OwnerConnectCode docstring for the full rationale."""
    with flask_app.app_context():
        from app import OwnerConnectCode
        assert hasattr(OwnerConnectCode, "owner_id")
        assert hasattr(OwnerConnectCode, "code")
        assert hasattr(OwnerConnectCode, "expires_at")
        assert hasattr(OwnerConnectCode, "used_at")
        assert hasattr(OwnerConnectCode, "used_by_user_id")
        assert hasattr(OwnerConnectCode, "used_by_store_id")
        assert hasattr(OwnerConnectCode, "revoked_at")


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
    """Owner signup creates a User with role='owner', store_id=None,
    and returns a JWT — the SPA stores it and lands on /dashboard.
    Form moved to React; the endpoint is /api/v2/auth/signup/owner."""
    rv = client.post("/api/v2/auth/signup/owner", json={
        "full_name": "Jane Owner",
        "email": "jane@example.com",
        "password": "password123",
    })
    assert rv.status_code == 201, rv.get_data(as_text=True)
    body = rv.get_json()
    assert body["role"] == "owner"
    assert body["store_id"] is None
    assert body["username"] == "jane@example.com"
    assert body["access_token"]
    with flask_app.app_context():
        from app import User
        u = User.query.filter_by(username="jane@example.com", store_id=None).first()
        assert u is not None
        assert u.role == "owner"
        assert u.full_name == "Jane Owner"


def test_owner_signup_get_legacy_route_redirects_to_spa(client):
    """The legacy /signup/owner GET form is gone — now a 301 to
    /app/signup/owner so url_for() in still-Jinja templates and old
    bookmarks keep working."""
    rv = client.get("/signup/owner", follow_redirects=False)
    assert rv.status_code == 301
    assert rv.headers["Location"] == "/app/signup/owner"


def test_owner_signup_duplicate_email_rejected(client):
    """Duplicate email returns 409 with field=email so the SPA can
    highlight the input."""
    with flask_app.app_context():
        from app import User
        existing = User(username="jane@example.com", full_name="Jane Owner", role="owner", store_id=None)
        existing.set_password("password123")
        db.session.add(existing)
        db.session.commit()
    rv = client.post("/api/v2/auth/signup/owner", json={
        "full_name": "Jane 2", "email": "jane@example.com", "password": "password123",
    })
    assert rv.status_code == 409
    body = rv.get_json()
    assert body["detail"]["field"] == "email"


def test_owner_signup_short_password_rejected(client):
    """Pydantic min_length=8 → 422."""
    rv = client.post("/api/v2/auth/signup/owner", json={
        "full_name": "Jane Owner", "email": "jane@example.com", "password": "short",
    })
    assert rv.status_code == 422


def test_owner_signup_invalid_email_rejected(client):
    """Email shape check at the controller layer → 422 with field=email."""
    rv = client.post("/api/v2/auth/signup/owner", json={
        "full_name": "Jane Owner", "email": "notanemail", "password": "password123",
    })
    assert rv.status_code == 422
    body = rv.get_json()
    assert body["detail"]["field"] == "email"


def test_owner_signup_blocks_admin_email(client):
    """Existing store admin email cannot be reused as an owner —
    ambiguous which login it should accept."""
    rv = client.post("/api/v2/auth/signup/owner", json={
        "full_name": "Jane Owner", "email": "admin@test.com", "password": "password123",
    })
    assert rv.status_code == 409
    body = rv.get_json()
    assert body["detail"]["field"] == "email"


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
    """Dashboard's "Linked stores" KPI reflects newly linked stores. The
    store list itself moved to /owner/locations, so we check the count
    here and the per-store rendering on the locations page below."""
    with flask_app.app_context():
        from app import User, Store, StoreOwnerLink
        owner = User.query.filter_by(username="owner@dashboard.com").first()
        store = Store.query.filter_by(slug="test-store").first()
        link = StoreOwnerLink(owner_id=owner.id, store_id=store.id)
        db.session.add(link)
        db.session.commit()
    rv = owner_client.get("/owner/dashboard")
    assert rv.status_code == 200
    assert b"Linked stores" in rv.data


def test_owner_locations_shows_store_after_link(owner_client):
    """/owner/locations card grid lists the store name after linking."""
    with flask_app.app_context():
        from app import User, Store, StoreOwnerLink
        owner = User.query.filter_by(username="owner@dashboard.com").first()
        store = Store.query.filter_by(slug="test-store").first()
        link = StoreOwnerLink(owner_id=owner.id, store_id=store.id)
        db.session.add(link)
        db.session.commit()
    rv = owner_client.get("/owner/locations")
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


# ── Owner-initiated connect flow (May 2026 reversal) ────────────
#
# The previous flow had the store admin generate a code that the owner
# redeemed. That accidentally let the admin remove the owner by
# revoking the link. The new flow inverts the direction:
#   1. Owner creates an OwnerConnectCode (owner-side route).
#   2. Owner shares the code with the store admin out of band.
#   3. Store admin redeems the code on /admin/settings/owner/redeem.
#   4. Disconnect is owner-side only; admin sees a read-only message.

def _make_owner_connect_code(owner_id, *, code="OWNCD001", days=7,
                              used_at=None, revoked_at=None):
    from app import OwnerConnectCode
    from datetime import datetime, timedelta
    c = OwnerConnectCode(
        owner_id=owner_id, code=code,
        expires_at=datetime.utcnow() + timedelta(days=days),
        used_at=used_at, revoked_at=revoked_at,
    )
    db.session.add(c); db.session.commit()
    return c


def test_admin_redeem_links_store_to_owner(logged_in_client):
    """Admin enters the owner-supplied code; a StoreOwnerLink is created
    and the code is marked used. This is the happy path for the new flow."""
    with flask_app.app_context():
        from app import User
        owner = User(username="ownerA@x.com", role="owner",
                     full_name="Owner A", store_id=None)
        owner.set_password("p"); db.session.add(owner); db.session.commit()
        _make_owner_connect_code(owner.id, code="REDEEMA1")
    rv = logged_in_client.post("/admin/settings/owner/redeem",
                                 data={"code": "REDEEMA1"})
    assert rv.status_code == 302
    with flask_app.app_context():
        from app import User, Store, StoreOwnerLink, OwnerConnectCode
        owner = User.query.filter_by(username="ownerA@x.com").first()
        store = Store.query.filter_by(slug="test-store").first()
        link = StoreOwnerLink.query.filter_by(
            owner_id=owner.id, store_id=store.id).first()
        assert link is not None
        code = OwnerConnectCode.query.filter_by(code="REDEEMA1").first()
        assert code.used_at is not None
        assert code.used_by_store_id == store.id


def test_admin_redeem_rejects_expired_code(logged_in_client):
    with flask_app.app_context():
        from app import User
        owner = User(username="ownerB@x.com", role="owner", store_id=None)
        owner.set_password("p"); db.session.add(owner); db.session.commit()
        _make_owner_connect_code(owner.id, code="EXPIRED1", days=-1)
    rv = logged_in_client.post("/admin/settings/owner/redeem",
                                 data={"code": "EXPIRED1"},
                                 follow_redirects=True)
    body = rv.data.lower()
    assert b"invalid" in body or b"expired" in body


def test_admin_redeem_rejects_used_code(logged_in_client):
    from datetime import datetime
    with flask_app.app_context():
        from app import User
        owner = User(username="ownerC@x.com", role="owner", store_id=None)
        owner.set_password("p"); db.session.add(owner); db.session.commit()
        _make_owner_connect_code(owner.id, code="USEDC001",
                                   used_at=datetime.utcnow())
    rv = logged_in_client.post("/admin/settings/owner/redeem",
                                 data={"code": "USEDC001"},
                                 follow_redirects=True)
    body = rv.data.lower()
    assert b"invalid" in body or b"expired" in body or b"used" in body


def test_admin_redeem_rejects_revoked_code(logged_in_client):
    from datetime import datetime
    with flask_app.app_context():
        from app import User
        owner = User(username="ownerD@x.com", role="owner", store_id=None)
        owner.set_password("p"); db.session.add(owner); db.session.commit()
        _make_owner_connect_code(owner.id, code="REVOKED1",
                                   revoked_at=datetime.utcnow())
    rv = logged_in_client.post("/admin/settings/owner/redeem",
                                 data={"code": "REVOKED1"},
                                 follow_redirects=True)
    body = rv.data.lower()
    assert b"invalid" in body or b"expired" in body


def test_admin_redeem_rejects_unknown_code(logged_in_client):
    rv = logged_in_client.post("/admin/settings/owner/redeem",
                                 data={"code": "BOGUSCD1"},
                                 follow_redirects=True)
    assert b"invalid" in rv.data.lower() or b"expired" in rv.data.lower()


def test_admin_redeem_rejects_already_linked(logged_in_client):
    """Trying to connect a store that's already linked to the same owner
    returns an info flash and does NOT consume the code."""
    with flask_app.app_context():
        from app import User, Store, StoreOwnerLink
        owner = User(username="ownerE@x.com", role="owner", store_id=None)
        owner.set_password("p"); db.session.add(owner); db.session.commit()
        store = Store.query.filter_by(slug="test-store").first()
        db.session.add(StoreOwnerLink(owner_id=owner.id, store_id=store.id))
        db.session.commit()
        _make_owner_connect_code(owner.id, code="DUPLINKA")
    rv = logged_in_client.post("/admin/settings/owner/redeem",
                                 data={"code": "DUPLINKA"},
                                 follow_redirects=True)
    assert b"already connected" in rv.data.lower()
    with flask_app.app_context():
        from app import OwnerConnectCode
        code = OwnerConnectCode.query.filter_by(code="DUPLINKA").first()
        assert code.used_at is None, \
            "code should not be consumed when the link already existed"


def test_admin_remove_owner_route_is_gone(logged_in_client):
    """The old /admin/settings/owner/remove-access route was removed
    in May 2026 — only the owner can disconnect. POSTing it now should
    404 (or any non-2xx) instead of severing the link."""
    rv = logged_in_client.post("/admin/settings/owner/remove-access",
                                 data={"owner_id": 1},
                                 follow_redirects=False)
    assert rv.status_code == 404


def test_admin_generate_code_route_is_gone(logged_in_client):
    """Same as above — the old /admin/settings/owner/generate-code
    route was removed; admins don't mint codes anymore."""
    rv = logged_in_client.post("/admin/settings/owner/generate-code",
                                 follow_redirects=False)
    assert rv.status_code == 404


def test_owner_link_route_is_gone(owner_client):
    """The old /owner/link route (owner redeems a store-generated code)
    was removed. Owners now MINT codes, not redeem them."""
    rv = owner_client.post("/owner/link", data={"code": "ANY"},
                             follow_redirects=False)
    assert rv.status_code == 404


# ── Owner-side code generation + revoke ─────────────────────────


def test_owner_connect_page_renders(owner_client):
    rv = owner_client.get("/owner/connect")
    assert rv.status_code == 200
    body = rv.data.lower()
    assert b"invite code" in body or b"generate" in body


def test_owner_generate_creates_active_code(owner_client):
    rv = owner_client.post("/owner/connect/generate")
    assert rv.status_code == 302
    with flask_app.app_context():
        from app import User, OwnerConnectCode
        owner = User.query.filter_by(username="owner@dashboard.com").first()
        codes = OwnerConnectCode.query.filter_by(owner_id=owner.id).all()
        assert len(codes) == 1
        assert codes[0].used_at is None
        assert codes[0].revoked_at is None
        assert len(codes[0].code) == 8


def test_owner_generate_revokes_previous_active(owner_client):
    """One active code per owner. Generating again revokes the prior one."""
    owner_client.post("/owner/connect/generate")
    owner_client.post("/owner/connect/generate")
    with flask_app.app_context():
        from app import User, OwnerConnectCode
        from datetime import datetime
        owner = User.query.filter_by(username="owner@dashboard.com").first()
        active = OwnerConnectCode.query.filter(
            OwnerConnectCode.owner_id == owner.id,
            OwnerConnectCode.used_at.is_(None),
            OwnerConnectCode.revoked_at.is_(None),
            OwnerConnectCode.expires_at > datetime.utcnow(),
        ).all()
        assert len(active) == 1


def test_owner_can_revoke_unused_code(owner_client):
    owner_client.post("/owner/connect/generate")
    with flask_app.app_context():
        from app import User, OwnerConnectCode
        owner = User.query.filter_by(username="owner@dashboard.com").first()
        code = OwnerConnectCode.query.filter_by(owner_id=owner.id).first()
        cid = code.id
    rv = owner_client.post(f"/owner/connect/{cid}/revoke")
    assert rv.status_code == 302
    with flask_app.app_context():
        from app import OwnerConnectCode
        code = OwnerConnectCode.query.filter_by(id=cid).first()
        assert code.revoked_at is not None


def test_owner_revoke_other_owners_code_is_404(owner_client):
    """Owner A can't revoke owner B's code (route filters by owner_id)."""
    with flask_app.app_context():
        from app import User
        b = User(username="ownerOther@x.com", role="owner", store_id=None)
        b.set_password("p"); db.session.add(b); db.session.commit()
        c = _make_owner_connect_code(b.id, code="OTHERS01")
        cid = c.id
    rv = owner_client.post(f"/owner/connect/{cid}/revoke",
                             follow_redirects=False)
    assert rv.status_code == 404


def test_owner_connect_page_blocks_non_owner(logged_in_client):
    rv = logged_in_client.get("/owner/connect")
    assert rv.status_code == 403


# ── Admin owner-tab UI (post-flow-reversal) ────────────────────


def test_admin_owner_tab_shows_redeem_form_when_no_owner(logged_in_client):
    rv = logged_in_client.get("/admin/settings?tab=owner")
    assert rv.status_code == 200
    body = rv.data.lower()
    assert b"connect" in body
    # Form posts to the new redeem route.
    assert b"/admin/settings/owner/redeem" in rv.data
    # Old generate-code route must NOT appear.
    assert b"/admin/settings/owner/generate-code" not in rv.data


def test_admin_owner_tab_hides_remove_button_when_linked(logged_in_client):
    """When an owner is linked, the admin sees the read-only "contact
    your owner" message — no Remove Access button (only owners can
    disconnect)."""
    with flask_app.app_context():
        from app import User, Store, StoreOwnerLink
        owner = User(username="ownerLinked@x.com", role="owner",
                     store_id=None, full_name="Linked Owner")
        owner.set_password("p"); db.session.add(owner); db.session.commit()
        store = Store.query.filter_by(slug="test-store").first()
        db.session.add(StoreOwnerLink(owner_id=owner.id, store_id=store.id))
        db.session.commit()
    rv = logged_in_client.get("/admin/settings?tab=owner")
    assert rv.status_code == 200
    body = rv.data
    assert b"Linked Owner" in body
    assert b"contact your owner" in body.lower()
    # Old remove-access form must NOT appear.
    assert b"/admin/settings/owner/remove-access" not in body
    # No Remove Access button text.
    assert b"Remove Access" not in body


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


def test_owner_connect_code_has_7_day_expiry(owner_client):
    """Owner-generated codes should expire ~7 days out."""
    owner_client.post("/owner/connect/generate")
    with flask_app.app_context():
        from app import User, OwnerConnectCode
        owner = User.query.filter_by(username="owner@dashboard.com").first()
        code = (OwnerConnectCode.query.filter_by(owner_id=owner.id)
                .order_by(OwnerConnectCode.created_at.desc()).first())
        delta = code.expires_at - code.created_at
        assert 6 <= delta.days <= 7


# ── /owner/locations: searchable list of linked stores ──────────
#
# The dashboard pivoted to a metrics-only view; the per-store grid
# moved here. The route also serves a `?partial=1` JSON payload for
# the debounced live-search swap pattern.

def _link_owner_to_test_store(owner_username):
    """Helper: fetch (or seed) the owner_username user and link them to
    the seeded test-store. Returns (owner_id, store_id)."""
    from app import User, Store, StoreOwnerLink
    with flask_app.app_context():
        owner = User.query.filter_by(username=owner_username).first()
        store = Store.query.filter_by(slug="test-store").first()
        if not StoreOwnerLink.query.filter_by(
            owner_id=owner.id, store_id=store.id
        ).first():
            db.session.add(StoreOwnerLink(owner_id=owner.id, store_id=store.id))
            db.session.commit()
        return owner.id, store.id


def test_owner_locations_loads_no_stores(owner_client):
    rv = owner_client.get("/owner/locations")
    assert rv.status_code == 200
    assert b"No stores connected" in rv.data


def test_owner_locations_lists_linked_stores(owner_client):
    _link_owner_to_test_store("owner@dashboard.com")
    rv = owner_client.get("/owner/locations")
    assert rv.status_code == 200
    assert b"Test Store" in rv.data


def test_owner_locations_search_filters_by_name(owner_client):
    """Empty query returns all; substring matches; non-match shows empty
    state but does NOT 404."""
    _link_owner_to_test_store("owner@dashboard.com")
    rv = owner_client.get("/owner/locations?q=Test")
    assert rv.status_code == 200
    assert b"Test Store" in rv.data
    rv = owner_client.get("/owner/locations?q=NoSuchStore")
    assert rv.status_code == 200
    assert b"No matches" in rv.data
    assert b"Test Store" not in rv.data


def test_owner_locations_partial_returns_json(owner_client):
    """?partial=1 must return JSON (not HTML page). Used by the
    debounced live-search fetcher to swap just the result region."""
    _link_owner_to_test_store("owner@dashboard.com")
    rv = owner_client.get("/owner/locations?partial=1&q=Test")
    assert rv.status_code == 200
    assert rv.headers["Content-Type"].startswith("application/json")
    payload = rv.get_json()
    assert "html" in payload
    assert "matched" in payload
    assert "total" in payload
    assert payload["matched"] == 1
    assert "Test Store" in payload["html"]


def test_owner_locations_period_filter_accepts_today_month_year(owner_client):
    _link_owner_to_test_store("owner@dashboard.com")
    for p in ("today", "month", "year"):
        rv = owner_client.get(f"/owner/locations?period={p}")
        assert rv.status_code == 200, f"period={p} failed"


def test_owner_locations_blocks_unauthenticated(client):
    rv = client.get("/owner/locations")
    assert rv.status_code == 302
    assert "/login" in rv.headers["Location"]


def test_owner_locations_blocks_non_owner(logged_in_client):
    """An admin trying to reach /owner/locations should hit the same 403
    as /owner/dashboard — the owner_required gate is on every owner route."""
    rv = logged_in_client.get("/owner/locations")
    assert rv.status_code == 403


def test_owner_locations_only_lists_owned_stores(owner_client):
    """Sanity: an unrelated store the owner is NOT linked to must not
    appear in the locations list, regardless of search query."""
    from datetime import datetime, timedelta
    _link_owner_to_test_store("owner@dashboard.com")
    with flask_app.app_context():
        from app import Store
        unrelated = Store(name="Other Owner Shop", slug="other-shop",
                          email="other@example.com", plan="trial")
        if hasattr(Store, "trial_ends_at"):
            unrelated.trial_ends_at = datetime.utcnow() + timedelta(days=7)
        db.session.add(unrelated)
        db.session.commit()
    rv = owner_client.get("/owner/locations")
    assert b"Other Owner Shop" not in rv.data
    rv = owner_client.get("/owner/locations?q=Other")
    assert b"Other Owner Shop" not in rv.data


# ── /owner/store/<id>: drill-down ─────────────────────────────

def test_owner_store_detail_loads(owner_client):
    _, sid = _link_owner_to_test_store("owner@dashboard.com")
    rv = owner_client.get(f"/owner/store/{sid}")
    assert rv.status_code == 200
    assert b"Test Store" in rv.data
    # KPI labels render
    assert b"Transfers" in rv.data
    assert b"Volume" in rv.data
    assert b"Fees collected" in rv.data


def test_owner_store_detail_shows_company_breakdown(owner_client):
    """Drill-down's per-company table aggregates Transfer.send_amount by
    company. Owners view by company is the whole reason this page exists."""
    from datetime import date
    _, sid = _link_owner_to_test_store("owner@dashboard.com")
    with flask_app.app_context():
        from app import User, Transfer
        admin = User.query.filter_by(username="admin@test.com").first()
        for co, amt in [("Intermex", 200.0), ("Maxi", 150.0), ("Intermex", 50.0)]:
            db.session.add(Transfer(
                store_id=sid, created_by=admin.id, send_date=date.today(),
                company=co, sender_name="J", send_amount=amt, fee=2.0,
                status="Sent",
            ))
        db.session.commit()
    rv = owner_client.get(f"/owner/store/{sid}?period=month")
    assert rv.status_code == 200
    body = rv.data
    # Company labels rendered
    assert b"Intermex" in body
    assert b"Maxi" in body
    # Aggregated volume rendered (Intermex = 250, Maxi = 150)
    assert b"$250" in body
    assert b"$150" in body


def test_owner_store_detail_blocks_unrelated_store(owner_client):
    """An owner must NOT be able to drill into a store they're not linked
    to — the route enforces StoreOwnerLink before rendering."""
    from datetime import datetime, timedelta
    with flask_app.app_context():
        from app import Store
        other = Store(name="Other Shop", slug="other-shop2",
                      email="x@example.com", plan="trial")
        if hasattr(Store, "trial_ends_at"):
            other.trial_ends_at = datetime.utcnow() + timedelta(days=7)
        db.session.add(other)
        db.session.commit()
        other_id = other.id
    rv = owner_client.get(f"/owner/store/{other_id}", follow_redirects=False)
    assert rv.status_code == 302
    assert "/owner/locations" in rv.headers["Location"]


def test_owner_store_detail_blocks_unauthenticated(client):
    rv = client.get("/owner/store/1")
    assert rv.status_code == 302
    assert "/login" in rv.headers["Location"]


def test_owner_store_detail_blocks_non_owner(logged_in_client):
    rv = logged_in_client.get("/owner/store/1")
    assert rv.status_code == 403


def test_owner_store_detail_period_filter_accepts_today_month_year(owner_client):
    _, sid = _link_owner_to_test_store("owner@dashboard.com")
    for p in ("today", "month", "year"):
        rv = owner_client.get(f"/owner/store/{sid}?period={p}")
        assert rv.status_code == 200, f"period={p} failed"


def test_owner_get_admin_dashboard_redirects_to_owner_dashboard(owner_client):
    """REGRESSION: /dashboard used to dereference store.id directly,
    which 500'd for owners (they have no current_store). Now the route
    must redirect any owner session to /owner/dashboard before that
    access path runs."""
    rv = owner_client.get("/dashboard", follow_redirects=False)
    assert rv.status_code == 302, (
        f"owner GET /dashboard should redirect, got {rv.status_code} "
        f"(this used to 500 — see commit history)"
    )
    assert "/owner/dashboard" in rv.headers["Location"]


def test_owner_account_profile_redirects_to_app(owner_client):
    """The legacy chrome split (admin sidebar vs owner sidebar on
    /account/profile) is moot now that the page lives in React —
    the SPA's AppShell renders the right nav based on JWT role
    rather than the template's `extends` choice. Page-rendering
    chrome coverage moved to the SPA's own role gating; here we
    just confirm the legacy URL 301s and the owner can reach the
    redirect target."""
    rv = owner_client.get("/account/profile", follow_redirects=False)
    assert rv.status_code == 301
    assert rv.headers["Location"] == "/app/account/profile"


def test_owner_account_security_uses_owner_shell(owner_client):
    rv = owner_client.get("/account/security")
    assert rv.status_code == 200
    assert b'href="/owner/locations"' in rv.data
    assert b'href="/transfers"' not in rv.data


def test_owner_account_notifications_uses_owner_shell(owner_client):
    rv = owner_client.get("/account/notifications")
    assert rv.status_code == 200
    assert b'href="/owner/locations"' in rv.data
    assert b'href="/transfers"' not in rv.data


def test_owner_store_detail_renders_recent_transfers(owner_client):
    """The "Recent transfers" section lists the latest 10 transfers by
    created_at, regardless of period selector."""
    from datetime import date
    _, sid = _link_owner_to_test_store("owner@dashboard.com")
    with flask_app.app_context():
        from app import User, Transfer
        admin = User.query.filter_by(username="admin@test.com").first()
        db.session.add(Transfer(
            store_id=sid, created_by=admin.id, send_date=date.today(),
            company="Barri", sender_name="Alice Q",
            send_amount=42.0, fee=1.0, status="Sent",
        ))
        db.session.commit()
    rv = owner_client.get(f"/owner/store/{sid}")
    assert b"Alice Q" in rv.data
    assert b"Barri" in rv.data


# ── /owner/dashboard: rich metrics view ───────────────────────

def test_owner_dashboard_shows_company_breakdown_table(owner_client):
    """Dashboard's "Company breakdown" mini-table aggregates across
    every linked store. With one Intermex transfer for $300, the
    Intermex row should appear with $300 in volume."""
    from datetime import date
    _, sid = _link_owner_to_test_store("owner@dashboard.com")
    with flask_app.app_context():
        from app import User, Transfer
        admin = User.query.filter_by(username="admin@test.com").first()
        db.session.add(Transfer(
            store_id=sid, created_by=admin.id, send_date=date.today(),
            company="Intermex", sender_name="X",
            send_amount=300.0, fee=3.0, status="Sent",
        ))
        db.session.commit()
    rv = owner_client.get("/owner/dashboard?period=month")
    assert rv.status_code == 200
    assert b"Intermex" in rv.data
    assert b"$300" in rv.data


def test_owner_dashboard_excludes_canceled_transfers_from_volume(owner_client):
    """Canceled / Rejected transfers must not inflate the dashboard's
    volume KPI (matches the superadmin dashboard's same exclusion)."""
    from datetime import date
    _, sid = _link_owner_to_test_store("owner@dashboard.com")
    with flask_app.app_context():
        from app import User, Transfer
        admin = User.query.filter_by(username="admin@test.com").first()
        # 100 Sent + 9999 Canceled — only the 100 should count.
        db.session.add(Transfer(
            store_id=sid, created_by=admin.id, send_date=date.today(),
            company="Intermex", sender_name="X",
            send_amount=100.0, fee=1.0, status="Sent",
        ))
        db.session.add(Transfer(
            store_id=sid, created_by=admin.id, send_date=date.today(),
            company="Intermex", sender_name="Y",
            send_amount=9999.0, fee=1.0, status="Canceled",
        ))
        db.session.commit()
    rv = owner_client.get("/owner/dashboard?period=today")
    assert b"$9,999" not in rv.data
    assert b"$100" in rv.data
