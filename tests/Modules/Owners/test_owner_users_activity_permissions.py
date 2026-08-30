"""HTTP integration tests for the owner user/permissions/activity
surface:

  GET  /api/v2/owner/users
  GET  /api/v2/owner/store/{store_id}/permissions
  PUT  /api/v2/owner/store/{store_id}/permissions
  POST /api/v2/owner/store/{store_id}/permissions/reset
  GET  /api/v2/owner/activity
  POST /api/v2/owner/bulk-permissions
"""
from tests._app import db, db_session


# ── Helpers ─────────────────────────────────────────────────


def _make_owner(*, username="boss-oup@x.com", password="ownerpass1!"):
    from api.Modules.Tenancy.Models import Store, User
    s = Store(name="Boss OUP Home", slug="boss-oup",
              email=username, plan="basic")
    db.session.add(s); db.session.commit()
    u = User(
        store_id=s.id, username=username, full_name="Boss OUP",
        email=username, role="owner",
    )
    u.set_password(password)
    db.session.add(u); db.session.commit()
    return u.id, s.id, password


def _link_store(owner_id, *, name="Sibling", slug="sibling-oup"):
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


def _seed_employee(store_id, *, username, full_name="Some Employee"):
    from api.Modules.Tenancy.Models import User
    u = User(
        store_id=store_id, username=username, full_name=full_name,
        role="employee",
    )
    u.set_password("emppass1!")
    db.session.add(u); db.session.commit()
    return u.id


# ── GET /owner/users ────────────────────────────────────────


def test_owner_users_requires_jwt(client):
    resp = client.get("/api/v2/owner/users")
    assert resp.status_code == 401


def test_owner_users_rejects_admin_role(client, test_store_id):
    token = _login_admin(client, test_store_id)
    resp = client.get(
        "/api/v2/owner/users",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403


def test_owner_users_empty_envelope_for_unlinked_owner(client):
    with db_session():
        _, _, pw = _make_owner()
    token = _login_owner(client, "boss-oup@x.com", pw)
    resp = client.get(
        "/api/v2/owner/users",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body == {"rows": [], "total": 0, "page": 1, "total_pages": 1}


def test_owner_users_lists_across_umbrella_stores(client):
    with db_session():
        owner_id, home_id, pw = _make_owner()
        sid_a = _link_store(owner_id, name="A OUP", slug="a-oup")
        sid_b = _link_store(owner_id, name="B OUP", slug="b-oup")
        _seed_employee(sid_a, username="alice@oup.com", full_name="Alice")
        _seed_employee(sid_b, username="bob@oup.com", full_name="Bob")
    token = _login_owner(client, "boss-oup@x.com", pw)
    resp = client.get(
        "/api/v2/owner/users",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    body = resp.get_json()
    usernames = {r["username"] for r in body["rows"]}
    # The owner's own home-store login is in the umbrella too.
    assert {"alice@oup.com", "bob@oup.com"} <= usernames
    for r in body["rows"]:
        if r["username"] == "alice@oup.com":
            assert r["store_name"] == "A OUP"
            assert r["role"] == "employee"


def test_owner_users_filters_by_store_id(client):
    with db_session():
        owner_id, _, pw = _make_owner()
        sid_a = _link_store(owner_id, name="A Filt", slug="a-filt")
        sid_b = _link_store(owner_id, name="B Filt", slug="b-filt")
        _seed_employee(sid_a, username="alice-f@oup.com")
        _seed_employee(sid_b, username="bob-f@oup.com")
    token = _login_owner(client, "boss-oup@x.com", pw)
    resp = client.get(
        f"/api/v2/owner/users?store_id={sid_a}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert all(r["store_id"] == sid_a for r in body["rows"])
    usernames = {r["username"] for r in body["rows"]}
    assert "alice-f@oup.com" in usernames
    assert "bob-f@oup.com" not in usernames


def test_owner_users_rejects_store_outside_umbrella(client):
    from api.Modules.Tenancy.Models import Store
    with db_session():
        owner_id, _, pw = _make_owner()
        _link_store(owner_id, name="In OUP", slug="in-oup")
        outsider = Store(name="Outsider OUP", slug="outsider-oup",
                          email="outsider-oup@x.com", plan="basic")
        db.session.add(outsider); db.session.commit()
        sid_out = outsider.id
    token = _login_owner(client, "boss-oup@x.com", pw)
    resp = client.get(
        f"/api/v2/owner/users?store_id={sid_out}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403


# ── GET/PUT /owner/store/{id}/permissions ──────────────────


def test_get_store_permissions_requires_jwt(client):
    resp = client.get("/api/v2/owner/store/1/permissions")
    assert resp.status_code == 401


def test_get_store_permissions_rejects_store_outside_umbrella(client):
    from api.Modules.Tenancy.Models import Store
    with db_session():
        owner_id, _, pw = _make_owner()
        outsider = Store(name="Outsider Perm", slug="outsider-perm",
                          email="outsider-perm@x.com", plan="basic")
        db.session.add(outsider); db.session.commit()
        sid_out = outsider.id
    token = _login_owner(client, "boss-oup@x.com", pw)
    resp = client.get(
        f"/api/v2/owner/store/{sid_out}/permissions",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403


def test_get_store_permissions_happy_path(client):
    with db_session():
        owner_id, _, pw = _make_owner()
        sid = _link_store(owner_id, name="Perm Store", slug="perm-store")
    token = _login_owner(client, "boss-oup@x.com", pw)
    resp = client.get(
        f"/api/v2/owner/store/{sid}/permissions",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["roles"] == ["admin", "employee"]
    assert body["editable_roles"] == ["employee"]
    assert "employee" in body["matrix"]
    assert "admin" in body["matrix"]


def test_put_store_permissions_matrix_mode_updates_employee(client):
    with db_session():
        owner_id, _, pw = _make_owner()
        sid = _link_store(owner_id, name="Matrix Store", slug="matrix-store")
    token = _login_owner(client, "boss-oup@x.com", pw)
    resp = client.put(
        f"/api/v2/owner/store/{sid}/permissions",
        json={"matrix": {
            "employee": {
                "settings": {"read": True, "create": False,
                             "update": False, "delete": True},
            },
        }},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, resp.get_data(as_text=True)
    body = resp.get_json()
    assert body["matrix"]["employee"]["settings"]["delete"] is True
    assert "employee" in body["has_overrides"]


def test_put_store_permissions_changes_mode_updates_employee(client):
    with db_session():
        owner_id, _, pw = _make_owner()
        sid = _link_store(owner_id, name="Changes Store", slug="changes-store")
    token = _login_owner(client, "boss-oup@x.com", pw)
    resp = client.put(
        f"/api/v2/owner/store/{sid}/permissions",
        json={"changes": [
            {"role": "employee", "resource": "settings",
             "action": "delete", "allowed": True},
        ]},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, resp.get_data(as_text=True)
    body = resp.get_json()
    assert body["matrix"]["employee"]["settings"]["delete"] is True


def test_put_store_permissions_rejects_editing_admin_role(client):
    with db_session():
        owner_id, _, pw = _make_owner()
        sid = _link_store(owner_id, name="Admin Edit Store", slug="admin-edit-store")
    token = _login_owner(client, "boss-oup@x.com", pw)
    resp = client.put(
        f"/api/v2/owner/store/{sid}/permissions",
        json={"matrix": {
            "admin": {"transfers": {"read": True, "create": False,
                                     "update": False, "delete": False}},
        }},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403


def test_put_store_permissions_rejects_store_outside_umbrella(client):
    from api.Modules.Tenancy.Models import Store
    with db_session():
        owner_id, _, pw = _make_owner()
        outsider = Store(name="Outsider Put", slug="outsider-put",
                          email="outsider-put@x.com", plan="basic")
        db.session.add(outsider); db.session.commit()
        sid_out = outsider.id
    token = _login_owner(client, "boss-oup@x.com", pw)
    resp = client.put(
        f"/api/v2/owner/store/{sid_out}/permissions",
        json={"changes": [
            {"role": "employee", "resource": "settings",
             "action": "delete", "allowed": True},
        ]},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403


def test_put_store_permissions_writes_audit_and_invalidates_sessions(client):
    from api.Modules.Audit.Models import OperatorAuditLog
    from api.Modules.Auth.Models import RefreshToken
    with db_session():
        owner_id, _, pw = _make_owner()
        sid = _link_store(owner_id, name="Audit Perm Store", slug="audit-perm-store")
        emp_id = _seed_employee(sid, username="revoke-me@oup.com")
    # log the employee in so there's a live refresh token to revoke
    resp_login = client.post(
        "/api/v2/auth/login",
        json={"username": "revoke-me@oup.com", "password": "emppass1!",
              "store_id": sid},
    )
    assert resp_login.status_code == 200

    token = _login_owner(client, "boss-oup@x.com", pw)
    resp = client.put(
        f"/api/v2/owner/store/{sid}/permissions",
        json={"changes": [
            {"role": "employee", "resource": "settings",
             "action": "delete", "allowed": True},
        ]},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    with db_session():
        rows = (
            db.session.query(OperatorAuditLog)
              .filter(
                  OperatorAuditLog.target_type == "store_role_override",
                  OperatorAuditLog.action == "update_store_permissions",
                  OperatorAuditLog.store_id == sid,
              )
              .all()
        )
        assert len(rows) == 1
        live = (
            db.session.query(RefreshToken)
              .filter(
                  RefreshToken.user_id == emp_id,
                  RefreshToken.revoked_at.is_(None),
              )
              .count()
        )
        assert live == 0


# ── POST /owner/store/{id}/permissions/reset ───────────────


def test_reset_store_permissions_requires_jwt(client):
    resp = client.post(
        "/api/v2/owner/store/1/permissions/reset",
        json={"role": "employee"},
    )
    assert resp.status_code == 401


def test_reset_store_permissions_rejects_non_employee_role(client):
    with db_session():
        owner_id, _, pw = _make_owner()
        sid = _link_store(owner_id, name="Reset Bad Role", slug="reset-bad-role")
    token = _login_owner(client, "boss-oup@x.com", pw)
    resp = client.post(
        f"/api/v2/owner/store/{sid}/permissions/reset",
        json={"role": "admin"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403


def test_reset_store_permissions_rejects_store_outside_umbrella(client):
    from api.Modules.Tenancy.Models import Store
    with db_session():
        owner_id, _, pw = _make_owner()
        outsider = Store(name="Outsider Reset", slug="outsider-reset",
                          email="outsider-reset@x.com", plan="basic")
        db.session.add(outsider); db.session.commit()
        sid_out = outsider.id
    token = _login_owner(client, "boss-oup@x.com", pw)
    resp = client.post(
        f"/api/v2/owner/store/{sid_out}/permissions/reset",
        json={"role": "employee"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403


def test_reset_store_permissions_happy_path_removes_overrides(client):
    from api.Modules.Audit.Models import OperatorAuditLog
    with db_session():
        owner_id, _, pw = _make_owner()
        sid = _link_store(owner_id, name="Reset OK Store", slug="reset-ok-store")
    token = _login_owner(client, "boss-oup@x.com", pw)
    headers = {"Authorization": f"Bearer {token}"}
    # First create an override.
    client.put(
        f"/api/v2/owner/store/{sid}/permissions",
        json={"changes": [
            {"role": "employee", "resource": "settings",
             "action": "delete", "allowed": True},
        ]},
        headers=headers,
    )
    check = client.get(
        f"/api/v2/owner/store/{sid}/permissions", headers=headers,
    )
    assert "employee" in check.get_json()["has_overrides"]

    resp = client.post(
        f"/api/v2/owner/store/{sid}/permissions/reset",
        json={"role": "employee"},
        headers=headers,
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert "employee" not in body["has_overrides"]
    with db_session():
        rows = (
            db.session.query(OperatorAuditLog)
              .filter(
                  OperatorAuditLog.target_type == "store_role_override",
                  OperatorAuditLog.action == "reset_store_permissions",
                  OperatorAuditLog.store_id == sid,
              )
              .all()
        )
        assert len(rows) == 1


# ── GET /owner/activity ─────────────────────────────────────


def test_owner_activity_requires_jwt(client):
    resp = client.get("/api/v2/owner/activity")
    assert resp.status_code == 401


def test_owner_activity_empty_envelope_for_unlinked_owner(client):
    with db_session():
        _, _, pw = _make_owner()
    token = _login_owner(client, "boss-oup@x.com", pw)
    resp = client.get(
        "/api/v2/owner/activity",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body == {"rows": [], "total": 0, "page": 1, "total_pages": 1}


def test_owner_activity_merges_operator_and_transfer_audit(client):
    from api.Modules.Audit.Models import OperatorAuditLog, TransferAudit
    with db_session():
        owner_id, _, pw = _make_owner()
        sid = _link_store(owner_id, name="Activity Store", slug="activity-store")
        db.session.add(OperatorAuditLog(
            store_id=sid, user_name="Alice", user_role="admin",
            target_type="user", action="create",
            summary="created a widget",
        ))
        db.session.add(TransferAudit(
            store_id=sid, transfer_id=1, employee_name="Bob",
            action="created", summary="created transfer #1",
        ))
        db.session.commit()
    token = _login_owner(client, "boss-oup@x.com", pw)
    resp = client.get(
        "/api/v2/owner/activity",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["total"] == 2
    types = {r["type"] for r in body["rows"]}
    assert types == {"audit", "transfer"}
    audit_row = next(r for r in body["rows"] if r["type"] == "audit")
    assert audit_row["user_name"] == "Alice"
    assert audit_row["store_name"] == "Activity Store"
    transfer_row = next(r for r in body["rows"] if r["type"] == "transfer")
    assert transfer_row["user_name"] == "Bob"
    assert transfer_row["target_label"] == "1"


def test_owner_activity_filters_by_search_term(client):
    from api.Modules.Audit.Models import OperatorAuditLog
    with db_session():
        owner_id, _, pw = _make_owner()
        sid = _link_store(owner_id, name="Search Store", slug="search-store")
        db.session.add(OperatorAuditLog(
            store_id=sid, user_name="Alice", user_role="admin",
            target_type="user", action="create",
            summary="findable needle event",
        ))
        db.session.add(OperatorAuditLog(
            store_id=sid, user_name="Carl", user_role="admin",
            target_type="user", action="create",
            summary="unrelated event",
        ))
        db.session.commit()
    token = _login_owner(client, "boss-oup@x.com", pw)
    resp = client.get(
        "/api/v2/owner/activity?q=needle",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["total"] == 1
    assert body["rows"][0]["summary"] == "findable needle event"


def test_owner_activity_rejects_store_outside_umbrella(client):
    from api.Modules.Tenancy.Models import Store
    with db_session():
        owner_id, _, pw = _make_owner()
        _link_store(owner_id, name="In Activity", slug="in-activity")
        outsider = Store(name="Outsider Activity", slug="outsider-activity",
                          email="outsider-activity@x.com", plan="basic")
        db.session.add(outsider); db.session.commit()
        sid_out = outsider.id
    token = _login_owner(client, "boss-oup@x.com", pw)
    resp = client.get(
        f"/api/v2/owner/activity?store_id={sid_out}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403


# ── POST /owner/bulk-permissions ────────────────────────────


def test_bulk_permissions_requires_jwt(client):
    resp = client.post(
        "/api/v2/owner/bulk-permissions",
        json={"store_ids": [1], "changes": []},
    )
    assert resp.status_code == 401


def test_bulk_permissions_rejects_admin_role(client, test_store_id):
    token = _login_admin(client, test_store_id)
    resp = client.post(
        "/api/v2/owner/bulk-permissions",
        json={"store_ids": [test_store_id], "changes": []},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403


def test_bulk_permissions_requires_linked_stores(client):
    with db_session():
        _, _, pw = _make_owner()
    token = _login_owner(client, "boss-oup@x.com", pw)
    resp = client.post(
        "/api/v2/owner/bulk-permissions",
        json={"store_ids": [1], "changes": [
            {"role": "employee", "resource": "settings",
             "action": "read", "allowed": True},
        ]},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422


def test_bulk_permissions_requires_store_ids_and_changes(client):
    with db_session():
        owner_id, _, pw = _make_owner()
        _link_store(owner_id, name="Req Fields", slug="req-fields")
    token = _login_owner(client, "boss-oup@x.com", pw)
    resp = client.post(
        "/api/v2/owner/bulk-permissions",
        json={"store_ids": [], "changes": []},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422


def test_bulk_permissions_applies_to_every_umbrella_store(client):
    from api.Modules.Audit.Models import OperatorAuditLog
    with db_session():
        owner_id, _, pw = _make_owner()
        sid_a = _link_store(owner_id, name="Bulk A", slug="bulk-a")
        sid_b = _link_store(owner_id, name="Bulk B", slug="bulk-b")
    token = _login_owner(client, "boss-oup@x.com", pw)
    resp = client.post(
        "/api/v2/owner/bulk-permissions",
        json={
            "store_ids": [sid_a, sid_b],
            "changes": [
                {"role": "employee", "resource": "settings",
                 "action": "delete", "allowed": True},
            ],
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, resp.get_data(as_text=True)
    body = resp.get_json()
    by_store = {r["store_id"]: r for r in body["results"]}
    assert by_store[sid_a]["status"] == "applied"
    assert by_store[sid_a]["changes"] == 1
    assert by_store[sid_b]["status"] == "applied"
    with db_session():
        rows = (
            db.session.query(OperatorAuditLog)
              .filter(
                  OperatorAuditLog.target_type == "store_role_override",
                  OperatorAuditLog.action == "bulk_update_store_permissions",
                  OperatorAuditLog.store_id.in_([sid_a, sid_b]),
              )
              .all()
        )
        assert len(rows) == 2


def test_bulk_permissions_rejects_store_outside_umbrella(client):
    from api.Modules.Tenancy.Models import Store
    with db_session():
        owner_id, _, pw = _make_owner()
        sid_a = _link_store(owner_id, name="Bulk In", slug="bulk-in")
        outsider = Store(name="Bulk Outsider", slug="bulk-outsider",
                          email="bulk-outsider@x.com", plan="basic")
        db.session.add(outsider); db.session.commit()
        sid_out = outsider.id
    token = _login_owner(client, "boss-oup@x.com", pw)
    resp = client.post(
        "/api/v2/owner/bulk-permissions",
        json={
            "store_ids": [sid_a, sid_out],
            "changes": [
                {"role": "employee", "resource": "settings",
                 "action": "delete", "allowed": True},
            ],
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    body = resp.get_json()
    by_store = {r["store_id"]: r["status"] for r in body["results"]}
    assert by_store[sid_a] == "applied"
    assert by_store[sid_out] == "rejected"


def test_bulk_permissions_no_op_when_values_already_match(client):
    """A change that doesn't flip anything (``allowed`` already
    matches the current matrix) reports 0 applied and skips the
    audit row for that store."""
    with db_session():
        owner_id, _, pw = _make_owner()
        sid = _link_store(owner_id, name="Bulk Noop", slug="bulk-noop")
    token = _login_owner(client, "boss-oup@x.com", pw)
    resp = client.post(
        "/api/v2/owner/bulk-permissions",
        json={
            "store_ids": [sid],
            "changes": [
                {"role": "employee", "resource": "settings",
                 "action": "delete", "allowed": False},
            ],
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["results"][0]["status"] == "applied"
    assert body["results"][0]["changes"] == 0
