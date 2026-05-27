"""HTTP integration tests for the owner bulk-add-user endpoint.

  POST /api/v2/owner/bulk-add-user
"""
from tests._app import db, db_session


def _make_owner(*, username="boss-bulk@x.com", password="ownerpass1!"):
    from api.Modules.Tenancy.Models import Store, User
    s = Store(name="Boss Bulk Home", slug="boss-bulk",
              email=username, plan="basic")
    db.session.add(s); db.session.commit()
    u = User(
        store_id=s.id, username=username, full_name="Boss",
        email=username, role="owner",
    )
    u.set_password(password)
    db.session.add(u); db.session.commit()
    return u.id, s.id, password


def _link_store(owner_id, *, name="Sibling Bulk", slug="sibling-bulk"):
    from api.Modules.Tenancy.Models import Store, StoreOwnerLink
    s = Store(name=name, slug=slug,
              email=f"{slug}@x.com", plan="basic")
    db.session.add(s); db.session.commit()
    db.session.add(StoreOwnerLink(owner_id=owner_id, store_id=s.id))
    db.session.commit()
    return s.id


def _login_owner(client, username, password):
    resp = client.post(
        "/api/v2/auth/login-cross-store",
        json={"username": username, "password": password},
    )
    return resp.get_json()["access_token"]


def _login_admin(client, store_id):
    resp = client.post(
        "/api/v2/auth/login",
        json={
            "username": "admin@test.com",
            "password": "testpass123!",
            "store_id": store_id,
        },
    )
    return resp.get_json()["access_token"]


# ── Auth gating ─────────────────────────────────────────────


def test_bulk_add_user_requires_jwt(client):
    resp = client.post(
        "/api/v2/owner/bulk-add-user",
        json={
            "username": "x@x.com", "password": "pw12345678",
            "store_ids": [1],
        },
    )
    assert resp.status_code == 401


def test_bulk_add_user_rejects_admin_role(client, test_store_id):
    """Only owners (or superadmin) can call this. A store admin's
    JWT carries role=admin, which the require-owner gate
    rejects with 403."""
    token = _login_admin(client, test_store_id)
    resp = client.post(
        "/api/v2/owner/bulk-add-user",
        json={
            "username": "x@x.com", "password": "pw12345678",
            "store_ids": [test_store_id],
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403


# ── Happy path ──────────────────────────────────────────────


def test_bulk_add_user_creates_at_every_umbrella_store(client):
    with db_session():
        owner_id, _, pw = _make_owner()
        sid_a = _link_store(owner_id, name="A", slug="a-bulk")
        sid_b = _link_store(owner_id, name="B", slug="b-bulk")
    token = _login_owner(client, "boss-bulk@x.com", pw)
    resp = client.post(
        "/api/v2/owner/bulk-add-user",
        json={
            "username": "regional@example.com",
            "password": "regional1!pw",
            "full_name": "Regional Manager",
            "role": "employee",
            "store_ids": [sid_a, sid_b],
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, resp.get_data(as_text=True)
    body = resp.get_json()
    assert body["created"]  == 2
    assert body["skipped"]  == 0
    assert body["rejected"] == 0
    assert len(body["results"]) == 2
    assert {r["status"] for r in body["results"]} == {"created"}
    # Verify both User rows landed.
    from api.Modules.Tenancy.Models import User
    with db_session():
        for sid in (sid_a, sid_b):
            u = (
                db.session.query(User)
                  .filter_by(store_id=sid, username="regional@example.com")
                  .one()
            )
            assert u.role == "employee"
            assert u.full_name == "Regional Manager"


def test_bulk_add_user_skips_existing_username_at_a_store(client):
    """The endpoint is best-effort — one store with an existing
    username doesn't fail the whole call. The other store still
    gets the create + the response surfaces the per-store
    outcome."""
    from api.Modules.Tenancy.Models import User
    with db_session():
        owner_id, _, pw = _make_owner()
        sid_a = _link_store(owner_id, name="A", slug="a-skip")
        sid_b = _link_store(owner_id, name="B", slug="b-skip")
        # Pre-seed an admin on sid_a with the same username we're
        # about to bulk-create.
        existing = User(
            store_id=sid_a, username="dup@example.com",
            role="employee", is_active=True,
        )
        existing.set_password("placeholder1!")
        db.session.add(existing); db.session.commit()
    token = _login_owner(client, "boss-bulk@x.com", pw)
    resp = client.post(
        "/api/v2/owner/bulk-add-user",
        json={
            "username": "dup@example.com",
            "password": "newpassword1!",
            "store_ids": [sid_a, sid_b],
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["created"] == 1
    assert body["skipped"] == 1
    by_store = {r["store_id"]: r["status"] for r in body["results"]}
    assert by_store[sid_a] == "skipped"
    assert by_store[sid_b] == "created"


def test_bulk_add_user_rejects_cross_umbrella_store(client):
    """A store_id outside the owner's umbrella surfaces as
    ``rejected`` rather than letting the call 403 the whole
    request — the operator's other (legit) store_ids still get
    processed."""
    from api.Modules.Tenancy.Models import Store
    with db_session():
        owner_id, _, pw = _make_owner()
        sid_a = _link_store(owner_id, name="In Umbrella", slug="in-umb")
        # Standalone store NOT linked to this owner.
        outsider = Store(
            name="Outsider", slug="outsider-bulk",
            email="outsider-bulk@x.com", plan="basic",
        )
        db.session.add(outsider); db.session.commit()
        sid_out = outsider.id
    token = _login_owner(client, "boss-bulk@x.com", pw)
    resp = client.post(
        "/api/v2/owner/bulk-add-user",
        json={
            "username": "mixedscope@example.com",
            "password": "mixedpass1!",
            "store_ids": [sid_a, sid_out],
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["created"]  == 1
    assert body["rejected"] == 1
    by_store = {r["store_id"]: r["status"] for r in body["results"]}
    assert by_store[sid_a]   == "created"
    assert by_store[sid_out] == "rejected"


def test_bulk_add_user_creates_audit_rows(client):
    """Every successful create writes one OperatorAuditLog row
    so the umbrella view shows the bulk activity per-store."""
    from api.Modules.Audit.Models import OperatorAuditLog
    with db_session():
        owner_id, _, pw = _make_owner()
        sid_a = _link_store(owner_id, name="A", slug="a-aud")
        sid_b = _link_store(owner_id, name="B", slug="b-aud")
    token = _login_owner(client, "boss-bulk@x.com", pw)
    resp = client.post(
        "/api/v2/owner/bulk-add-user",
        json={
            "username": "auditme@example.com",
            "password": "auditpass1!",
            "store_ids": [sid_a, sid_b],
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    with db_session():
        rows = (
            db.session.query(OperatorAuditLog)
              .filter(
                  OperatorAuditLog.target_type == "user",
                  OperatorAuditLog.action == "create",
                  OperatorAuditLog.store_id.in_([sid_a, sid_b]),
              )
              .all()
        )
        assert len(rows) == 2
        assert all("auditme@example.com" in r.summary for r in rows)


def test_bulk_add_user_rejects_short_password(client):
    """Pydantic ``min_length=8`` on password keeps the operator
    from creating a 1-char password by accident."""
    with db_session():
        owner_id, _, pw = _make_owner()
        sid = _link_store(owner_id, name="A", slug="a-pw")
    token = _login_owner(client, "boss-bulk@x.com", pw)
    resp = client.post(
        "/api/v2/owner/bulk-add-user",
        json={
            "username": "shortpw@example.com",
            "password": "abc",
            "store_ids": [sid],
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422


def test_bulk_add_user_rejects_empty_store_ids(client):
    """``min_length=1`` on store_ids — no point in a no-op
    bulk-create."""
    with db_session():
        _, _, pw = _make_owner()
    token = _login_owner(client, "boss-bulk@x.com", pw)
    resp = client.post(
        "/api/v2/owner/bulk-add-user",
        json={
            "username": "nostore@example.com",
            "password": "validpw12!",
            "store_ids": [],
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422


def test_bulk_add_user_rejects_bad_role(client):
    """Only 'employee' allowed — owners can't create admin-role users.
    'owner' / 'superadmin' must be created out-of-band via the signup flow."""
    with db_session():
        owner_id, _, pw = _make_owner()
        sid = _link_store(owner_id, name="A", slug="a-role")
    token = _login_owner(client, "boss-bulk@x.com", pw)
    resp = client.post(
        "/api/v2/owner/bulk-add-user",
        json={
            "username": "badrole@example.com",
            "password": "validpw12!",
            "role": "superadmin",
            "store_ids": [sid],
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422
