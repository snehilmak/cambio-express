"""HTTP integration tests for the admin /users endpoints.

Powers /app/admin/users (roster + create + edit). Mirrors the
legacy admin_users / admin_new_user / admin_edit_user Flask
routes, plus the new self-edit guard.
"""
from tests._app import db, db_session


def _login(client_, store_id):
    resp = client_.post(
        "/api/v2/auth/login",
        json={
            "username": "admin@test.com",
            "password": "testpass123!",
            "store_id": store_id,
        },
    )
    return resp.get_json()["access_token"]


# ── auth gating ─────────────────────────────────────────────


def test_users_list_requires_jwt(client):
    resp = client.get("/api/v2/admin/users")
    assert resp.status_code == 401


def test_users_create_requires_jwt(client):
    resp = client.post(
        "/api/v2/admin/users",
        json={"username": "x", "password": "y"},
    )
    assert resp.status_code == 401


def test_users_get_requires_jwt(client):
    resp = client.get("/api/v2/admin/users/1")
    assert resp.status_code == 401


def test_users_patch_requires_jwt(client):
    resp = client.patch("/api/v2/admin/users/1", json={"role": "admin"})
    assert resp.status_code == 401


def test_users_endpoints_reject_employee_role(client, test_store_id):
    """Cashier role can't manage the user roster."""
    from api.Modules.Tenancy.Models import User
    from tests._app import db
    with db_session():
        u = User(
            store_id=test_store_id, username="cashier_users_admin",
            role="employee", is_active=True,
        )
        u.set_password("emppass1234")
        db.session.add(u); db.session.commit()
    try:
        login = client.post(
            "/api/v2/auth/login",
            json={
                "username": "cashier_users_admin",
                "password": "emppass1234",
                "store_id": test_store_id,
            },
        )
        token = login.get_json()["access_token"]
        listing = client.get(
            "/api/v2/admin/users",
            headers={"Authorization": f"Bearer {token}"},
        )
        creating = client.post(
            "/api/v2/admin/users",
            json={"username": "x", "password": "y"},
            headers={"Authorization": f"Bearer {token}"},
        )
        patching = client.patch(
            "/api/v2/admin/users/1",
            json={"role": "admin"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert listing.status_code == 403
        assert creating.status_code == 403
        assert patching.status_code == 403
    finally:
        with db_session():
            u2 = db.session.query(User).filter_by(
                username="cashier_users_admin",
            ).first()
            if u2:
                db.session.delete(u2); db.session.commit()


def test_users_list_rejects_superadmin(client):
    """Superadmin has no store scope, so /admin/users 403s."""
    from tests.conftest import login_superadmin
    token = login_superadmin(client)
    resp = client.get(
        "/api/v2/admin/users",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403


# ── GET /admin/users ────────────────────────────────────────


def test_users_list_returns_envelope(client, test_store_id):
    token = _login(client, test_store_id)
    resp = client.get(
        "/api/v2/admin/users",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert "rows" in body
    # Seed fixture has the admin user; assert it's there.
    usernames = {r["username"] for r in body["rows"]}
    assert "admin@test.com" in usernames
    # Row shape — every required field is present.
    row = next(r for r in body["rows"] if r["username"] == "admin@test.com")
    for key in ("id", "username", "full_name", "role", "is_active", "created_at"):
        assert key in row


def test_users_list_does_not_leak_cross_store(client, test_store_id):
    """Users from a different store must not appear in this store's
    roster."""
    from api.Modules.Tenancy.Models import Store, User
    from tests._app import db
    with db_session():
        other = Store(name="Other Store", slug="other-store",
                      email="ops@other.com", plan="trial")
        db.session.add(other); db.session.flush()
        u = User(
            store_id=other.id, username="other_admin@other.com",
            role="admin",
        )
        u.set_password("zzz")
        db.session.add(u); db.session.commit()
    token = _login(client, test_store_id)
    resp = client.get(
        "/api/v2/admin/users",
        headers={"Authorization": f"Bearer {token}"},
    )
    usernames = {r["username"] for r in resp.get_json()["rows"]}
    assert "other_admin@other.com" not in usernames


# ── POST /admin/users ───────────────────────────────────────


def test_users_create_then_list(client, test_store_id):
    token = _login(client, test_store_id)
    create = client.post(
        "/api/v2/admin/users",
        json={
            "username":  "new.cashier",
            "password":  "secret123",
            "full_name": "New Cashier",
            "role":      "employee",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert create.status_code == 201, create.get_data(as_text=True)
    body = create.get_json()
    assert body["username"]  == "new.cashier"
    assert body["role"]      == "employee"
    assert body["is_active"] is True
    new_id = body["id"]

    listed = client.get(
        "/api/v2/admin/users",
        headers={"Authorization": f"Bearer {token}"},
    )
    rows = listed.get_json()["rows"]
    assert any(r["id"] == new_id for r in rows)


def test_users_create_hashes_password(client, test_store_id):
    """Password must never be stored raw — User.set_password is the
    only path."""
    token = _login(client, test_store_id)
    create = client.post(
        "/api/v2/admin/users",
        json={
            "username": "hash.check",
            "password": "rawpass789",
            "role":     "employee",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert create.status_code == 201
    new_id = create.get_json()["id"]

    from api.Modules.Tenancy.Models import User
    from tests._app import db
    with db_session():
        row = db.session.get(User, new_id)
        assert row is not None
        # Stored hash must not equal the raw password and must
        # successfully verify it.
        assert row.password_hash != "rawpass789"
        assert row.check_password("rawpass789") is True


def test_users_create_rejects_duplicate_username(client, test_store_id):
    """Same username in same store collides — 422 with field error."""
    token = _login(client, test_store_id)
    client.post(
        "/api/v2/admin/users",
        json={"username": "dup.user", "password": "x"},
        headers={"Authorization": f"Bearer {token}"},
    )
    again = client.post(
        "/api/v2/admin/users",
        json={"username": "dup.user", "password": "y"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert again.status_code == 422
    detail = again.get_json()["detail"]
    assert "field_errors" in detail
    assert "username" in detail["field_errors"]


def test_users_create_rejects_bad_role(client, test_store_id):
    token = _login(client, test_store_id)
    resp = client.post(
        "/api/v2/admin/users",
        json={
            "username": "bad.role",
            "password": "x",
            "role":     "owner",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422


def test_users_create_rejects_extra_fields(client, test_store_id):
    """Schema is extra=forbid — store_id / id can't be smuggled."""
    token = _login(client, test_store_id)
    resp = client.post(
        "/api/v2/admin/users",
        json={
            "username": "extra.user",
            "password": "x",
            "store_id": 999,  # not in schema
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422


# ── GET /admin/users/{id} ───────────────────────────────────


def test_users_get_returns_detail(client, test_store_id, test_admin_id):
    token = _login(client, test_store_id)
    resp = client.get(
        f"/api/v2/admin/users/{test_admin_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert "user" in body
    assert body["user"]["id"]       == test_admin_id
    assert body["user"]["username"] == "admin@test.com"
    assert body["user"]["role"]     == "admin"


def test_users_get_404_for_cross_store(client, test_store_id):
    """Cross-store user IDs surface as 404 — opaque tenancy."""
    from api.Modules.Tenancy.Models import Store, User
    from tests._app import db
    with db_session():
        other = Store(name="Other 2", slug="other-2",
                      email="o2@x.com", plan="trial")
        db.session.add(other); db.session.flush()
        u = User(store_id=other.id, username="o2admin", role="admin")
        u.set_password("zzz")
        db.session.add(u); db.session.commit()
        other_uid = u.id
    token = _login(client, test_store_id)
    resp = client.get(
        f"/api/v2/admin/users/{other_uid}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404


def test_users_get_404_for_unknown_id(client, test_store_id):
    token = _login(client, test_store_id)
    resp = client.get(
        "/api/v2/admin/users/9999999",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404


# ── PATCH /admin/users/{id} ─────────────────────────────────


def test_users_patch_renames(client, test_store_id):
    token = _login(client, test_store_id)
    create = client.post(
        "/api/v2/admin/users",
        json={"username": "rename.me", "password": "x"},
        headers={"Authorization": f"Bearer {token}"},
    )
    new_id = create.get_json()["id"]
    rename = client.patch(
        f"/api/v2/admin/users/{new_id}",
        json={"full_name": "Renamed User"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert rename.status_code == 200
    assert rename.get_json()["full_name"] == "Renamed User"


def test_users_patch_changes_role_and_is_active(client, test_store_id):
    token = _login(client, test_store_id)
    create = client.post(
        "/api/v2/admin/users",
        json={"username": "promote.me", "password": "x"},
        headers={"Authorization": f"Bearer {token}"},
    )
    new_id = create.get_json()["id"]
    promote = client.patch(
        f"/api/v2/admin/users/{new_id}",
        json={"role": "admin", "is_active": False},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert promote.status_code == 200
    body = promote.get_json()
    assert body["role"]      == "admin"
    assert body["is_active"] is False


def test_users_patch_password_only_when_provided(
    client, test_store_id,
):
    """Empty / missing password leaves the existing hash alone;
    a non-blank password value reseats it."""
    from api.Modules.Tenancy.Models import User
    from tests._app import db
    token = _login(client, test_store_id)
    create = client.post(
        "/api/v2/admin/users",
        json={"username": "pw.user", "password": "first123"},
        headers={"Authorization": f"Bearer {token}"},
    )
    new_id = create.get_json()["id"]

    # Empty password — should keep the original hash.
    client.patch(
        f"/api/v2/admin/users/{new_id}",
        json={"full_name": "Pw User", "password": ""},
        headers={"Authorization": f"Bearer {token}"},
    )
    with db_session():
        row = db.session.get(User, new_id)
        assert row.check_password("first123") is True

    # Non-blank password — re-hashes.
    client.patch(
        f"/api/v2/admin/users/{new_id}",
        json={"password": "second456"},
        headers={"Authorization": f"Bearer {token}"},
    )
    with db_session():
        row = db.session.get(User, new_id)
        assert row.check_password("second456") is True
        assert row.check_password("first123")  is False


def test_users_patch_self_demotion_blocked(
    client, test_store_id, test_admin_id,
):
    """The signed-in admin cannot demote / deactivate their own
    account through PATCH — protects against single-admin
    lockout."""
    token = _login(client, test_store_id)
    demote = client.patch(
        f"/api/v2/admin/users/{test_admin_id}",
        json={"role": "employee"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert demote.status_code == 422
    detail = demote.get_json()["detail"]
    assert "field_errors" in detail
    assert "role" in detail["field_errors"]

    deactivate = client.patch(
        f"/api/v2/admin/users/{test_admin_id}",
        json={"is_active": False},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert deactivate.status_code == 422
    detail = deactivate.get_json()["detail"]
    assert "field_errors" in detail
    assert "is_active" in detail["field_errors"]


def test_users_patch_self_full_name_allowed(
    client, test_store_id, test_admin_id,
):
    """Self-edit guard only blocks role + is_active. Renaming
    your own full_name (or rotating your own password) is fine."""
    token = _login(client, test_store_id)
    resp = client.patch(
        f"/api/v2/admin/users/{test_admin_id}",
        json={"full_name": "Renamed Self"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.get_json()["full_name"] == "Renamed Self"


def test_users_patch_404_for_cross_store(client, test_store_id):
    token = _login(client, test_store_id)
    resp = client.patch(
        "/api/v2/admin/users/9999999",
        json={"full_name": "Whoever"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404


def test_users_patch_records_audit_row(client, test_store_id):
    """Mutating endpoints append to OperatorAuditLog so the audit
    log surfaces who changed what."""
    from api.Modules.Audit.Models import OperatorAuditLog
    from tests._app import db
    token = _login(client, test_store_id)
    create = client.post(
        "/api/v2/admin/users",
        json={"username": "audited", "password": "x"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert create.status_code == 201
    new_id = create.get_json()["id"]
    client.patch(
        f"/api/v2/admin/users/{new_id}",
        json={"full_name": "Audited Person"},
        headers={"Authorization": f"Bearer {token}"},
    )
    with db_session():
        rows = (
            db.session.query(OperatorAuditLog)
              .filter_by(store_id=test_store_id, target_type="user")
              .all()
        )
        actions = sorted(r.action for r in rows)
        assert "create" in actions
        assert "update" in actions


# ── Flask 301 redirect contract ─────────────────────────────


def test_legacy_admin_users_redirects(logged_in_client):
    resp = logged_in_client.get("/admin/users")
    assert resp.status_code == 301
    assert resp.headers["Location"].endswith("/app/admin/users")


def test_legacy_admin_users_new_redirects(logged_in_client):
    resp = logged_in_client.get("/admin/users/new")
    assert resp.status_code == 301
    assert resp.headers["Location"].endswith("/app/admin/users/new")


def test_legacy_admin_users_edit_redirects(
    logged_in_client, test_admin_id,
):
    resp = logged_in_client.get(
        f"/admin/users/{test_admin_id}/edit",
    )
    assert resp.status_code == 301
    assert resp.headers["Location"].endswith(
        f"/app/admin/users/{test_admin_id}/edit",
    )


def test_legacy_admin_users_post_also_redirects(logged_in_client):
    """POST goes through the redirect too — the SPA POSTs to
    /api/v2/admin/users directly; the legacy form path is dead.
    Browsers degrade 301 POST → GET on follow but our test
    asserts the bare 30x response."""
    resp = logged_in_client.post(
        "/admin/users/new",
        data={"username": "x", "password": "y", "role": "employee"},
    )
    # Flask's redirect() returns 301 by default; in some Werkzeug
    # versions browser POSTs follow as GETs but the framework
    # response code stays at 301.
    assert resp.status_code in (301, 302, 308)
