"""Per-user permission overlays (R-1) — the "custom access" layer.

Security-critical. The invariants under test:
  * ``resolve_user_grants`` layers the ``user:<id>`` overlay above
    role resolution with per-resource mention semantics (a saved
    matrix is explicit for every current resource; resources added
    to the platform later fall through to the role),
  * ``check_permission(..., user_id=…)`` enforces the overlay;
    role-only callers keep exact pre-R-1 behavior,
  * the /admin/users/{id}/permissions endpoints guard writes
    (self-edit 422, cross-store 404, users.update required), audit
    them, and revoke the target's refresh tokens,
  * JWT perms baked at login reflect the overlay, AND enforcement
    is live — a token minted before the overlay still gets 403,
  * the dashboard summary drops every block the user can't read
    ("Amber can't see any numbers").
"""
from tests._app import db, db_session
from tests.conftest import login_admin, login_employee


def _headers(token):
    return {"Authorization": f"Bearer {token}"}


def _mk_store_user(store_id, username, role="employee",
                   password="emppass1234"):
    from api.Modules.Tenancy.Models import User
    with db_session():
        u = User(
            store_id=store_id, username=username,
            role=role, is_active=True,
        )
        u.set_password(password)
        db.session.add(u)
        db.session.commit()
        return u.id


HR_ONLY = {
    "time_clock": {"create": True, "read": True,
                   "update": True, "delete": True},
    "users": {"read": True},
}


# ── Core resolution ─────────────────────────────────────────


def test_overlay_layers_above_role(test_store_id):
    from api.Core.Permissions import (
        check_permission, clear_user_permissions,
        resolve_user_grants, set_user_permissions,
        user_has_custom_permissions,
    )
    uid = _mk_store_user(test_store_id, "r1_core_emp")
    assert user_has_custom_permissions(uid, test_store_id) is False
    # No overlay → identical to pure role resolution.
    assert check_permission(
        "employee", test_store_id, "daily_book", "read", user_id=uid,
    ) is True

    set_user_permissions(test_store_id, uid, HR_ONLY)
    try:
        assert user_has_custom_permissions(uid, test_store_id) is True
        grants = resolve_user_grants(uid, "employee", test_store_id)
        assert ("time_clock", "delete") in grants
        assert ("users", "read") in grants
        # Role defaults the save didn't grant are OFF — every
        # current resource was written explicitly (__none__).
        assert ("daily_book", "read") not in grants
        assert ("transfers", "create") not in grants
        assert check_permission(
            "employee", test_store_id, "daily_book", "read",
            user_id=uid,
        ) is False
        # Role-only callers are untouched by the overlay.
        assert check_permission(
            "employee", test_store_id, "daily_book", "read",
        ) is True
    finally:
        clear_user_permissions(test_store_id, uid)
    assert user_has_custom_permissions(uid, test_store_id) is False
    assert check_permission(
        "employee", test_store_id, "daily_book", "read", user_id=uid,
    ) is True


def test_unmentioned_resource_falls_through_to_role(test_store_id):
    """A resource with NO overlay rows (added to the platform after
    the matrix was saved) resolves from the role, not to off."""
    from api.Core.Permissions import (
        _get_enforcer, _user_subject, clear_user_permissions,
        reload_policy, resolve_user_grants, set_user_permissions,
    )
    uid = _mk_store_user(test_store_id, "r1_future_emp")
    set_user_permissions(test_store_id, uid, HR_ONLY)
    try:
        # Simulate "catalog didn't exist when this was saved" by
        # deleting its marker row.
        e = _get_enforcer()
        e.remove_filtered_policy(
            0, _user_subject(uid), str(test_store_id), "catalog",
        )
        e.save_policy()
        reload_policy()
        grants = resolve_user_grants(uid, "employee", test_store_id)
        # employee role default grants catalog.read → falls through.
        assert ("catalog", "read") in grants
        # Explicitly-off resources stay off.
        assert ("daily_book", "read") not in grants
    finally:
        clear_user_permissions(test_store_id, uid)


# ── Endpoint guards ─────────────────────────────────────────


def test_put_get_delete_roundtrip(client, test_store_id):
    token = login_admin(client, test_store_id)
    uid = _mk_store_user(test_store_id, "r1_amber")

    put = client.put(
        f"/api/v2/admin/users/{uid}/permissions",
        headers=_headers(token), json={"matrix": HR_ONLY},
    )
    assert put.status_code == 200, put.get_data(as_text=True)
    body = put.get_json()
    assert body["has_custom"] is True
    assert body["matrix"]["time_clock"]["delete"] is True
    assert body["matrix"]["users"]["read"] is True
    assert body["matrix"]["daily_book"]["read"] is False
    assert body["matrix"]["transfers"]["read"] is False

    got = client.get(
        f"/api/v2/admin/users/{uid}/permissions",
        headers=_headers(token),
    ).get_json()
    assert got["has_custom"] is True
    assert got["matrix"] == body["matrix"]

    # Roster + detail rows surface the flag for the SPA.
    roster = client.get(
        "/api/v2/admin/users", headers=_headers(token),
    ).get_json()["rows"]
    by_id = {r["id"]: r for r in roster}
    assert by_id[uid]["has_custom_permissions"] is True

    cleared = client.delete(
        f"/api/v2/admin/users/{uid}/permissions",
        headers=_headers(token),
    ).get_json()
    assert cleared["has_custom"] is False
    # Back to employee-role defaults.
    assert cleared["matrix"]["daily_book"]["read"] is True
    assert cleared["matrix"]["time_clock"]["delete"] is False


def test_write_guards(client, test_store_id):
    from api.Modules.Tenancy.Models import User
    token = login_admin(client, test_store_id)
    with db_session():
        admin_id = (
            db.session.query(User.id)
            .filter_by(store_id=test_store_id, role="admin")
            .first()
        )[0]

    # Self-edit refused — can't lock yourself out (or grant more).
    selfput = client.put(
        f"/api/v2/admin/users/{admin_id}/permissions",
        headers=_headers(token), json={"matrix": HR_ONLY},
    )
    assert selfput.status_code == 422

    # Unknown / cross-store ids are an opaque 404.
    missing = client.put(
        "/api/v2/admin/users/999999/permissions",
        headers=_headers(token), json={"matrix": HR_ONLY},
    )
    assert missing.status_code == 404

    # Matrix payload is required.
    uid = _mk_store_user(test_store_id, "r1_guard_emp")
    nobody = client.put(
        f"/api/v2/admin/users/{uid}/permissions",
        headers=_headers(token), json={},
    )
    assert nobody.status_code == 422

    # Cashiers can't manage overlays (users.update).
    emp_token = login_employee(
        client, test_store_id, "r1_guard_emp",
        password="emppass1234",
    )
    denied = client.put(
        f"/api/v2/admin/users/{uid}/permissions",
        headers=_headers(emp_token), json={"matrix": HR_ONLY},
    )
    assert denied.status_code == 403


def test_write_audits_and_revokes_sessions(client, test_store_id):
    from api.Modules.Audit.Models import OperatorAuditLog
    from api.Modules.Auth.Models import RefreshToken
    from api.Core.Permissions import clear_user_permissions

    token = login_admin(client, test_store_id)
    uid = _mk_store_user(test_store_id, "r1_audit_emp")
    # The target logs in → live refresh token exists.
    login_employee(
        client, test_store_id, "r1_audit_emp", password="emppass1234",
    )
    with db_session():
        assert (
            db.session.query(RefreshToken)
            .filter_by(user_id=uid, revoked_at=None).count()
        ) >= 1

    resp = client.put(
        f"/api/v2/admin/users/{uid}/permissions",
        headers=_headers(token), json={"matrix": HR_ONLY},
    )
    assert resp.status_code == 200
    try:
        with db_session():
            # Every live session for the target died with the write.
            assert (
                db.session.query(RefreshToken)
                .filter_by(user_id=uid, revoked_at=None).count()
            ) == 0
            audit = (
                db.session.query(OperatorAuditLog)
                .filter_by(
                    store_id=test_store_id,
                    action="set_user_permissions",
                    target_id=str(uid),
                )
                .first()
            )
            assert audit is not None
    finally:
        clear_user_permissions(test_store_id, uid)


# ── JWT baking + live enforcement ───────────────────────────


def test_jwt_perms_and_live_enforcement(client, test_store_id):
    from api.Core.Permissions import clear_user_permissions

    admin_token = login_admin(client, test_store_id)
    uid = _mk_store_user(test_store_id, "r1.live.emp@store.com")

    # Token minted BEFORE the overlay — carries full employee perms.
    pre_token = login_employee(
        client, test_store_id, "r1.live.emp@store.com", password="emppass1234",
    )
    assert client.get(
        f"/api/v2/transfers?store_ids={test_store_id}",
        headers=_headers(pre_token),
    ).status_code == 200

    put = client.put(
        f"/api/v2/admin/users/{uid}/permissions",
        headers=_headers(admin_token), json={"matrix": HR_ONLY},
    )
    assert put.status_code == 200
    try:
        # Live enforcement: the stale token is blocked immediately.
        assert client.get(
            f"/api/v2/transfers?store_ids={test_store_id}",
        headers=_headers(pre_token),
        ).status_code == 403

        # Fresh login bakes the restricted perms into the claim.
        login = client.post(
            "/api/v2/auth/login",
            json={
                "username": "r1.live.emp@store.com",
                "password": "emppass1234",
                "store_id": test_store_id,
            },
        ).get_json()
        perms = login["permissions"]
        assert "time_clock.read" in perms
        assert "transfers.read" not in perms
        assert "daily_book.read" not in perms
    finally:
        clear_user_permissions(test_store_id, uid)


def test_dashboard_hides_numbers_for_restricted_user(
    client, test_store_id,
):
    """The Amber scenario: HR-only access → the landing payload
    itself carries no sales / lottery / transfer numbers."""
    from api.Core.Permissions import clear_user_permissions, set_user_permissions

    uid = _mk_store_user(test_store_id, "r1_amber_dash")
    set_user_permissions(test_store_id, uid, HR_ONLY)
    try:
        token = login_employee(
            client, test_store_id, "r1_amber_dash",
            password="emppass1234",
        )
        summary = client.get(
            "/api/v2/dashboard/summary", headers=_headers(token),
        ).get_json()
        assert summary["role"] == "employee"
        assert summary["day_close"] is None
        assert summary["lottery"] is None
        assert summary["today_transfers"] == []
        assert summary["totals"]["count"] == 0
        assert summary["totals"]["sent"] == 0
    finally:
        clear_user_permissions(test_store_id, uid)


def test_dashboard_hides_numbers_for_restricted_admin(
    client, test_store_id,
):
    """Same overlay on an ADMIN-role user — the admin dashboard's
    financial blocks all disappear too."""
    from api.Core.Permissions import clear_user_permissions, set_user_permissions

    uid = _mk_store_user(
        test_store_id, "r1_amber_admin", role="admin",
    )
    set_user_permissions(test_store_id, uid, HR_ONLY)
    try:
        token = login_employee(
            client, test_store_id, "r1_amber_admin",
            password="emppass1234",
        )
        summary = client.get(
            "/api/v2/dashboard/summary", headers=_headers(token),
        ).get_json()
        assert summary["role"] == "admin"
        assert summary["sales"] is None
        assert summary["purchases"] is None
        assert summary["day_close"] is None
        assert summary["lottery"] is None
        assert summary["recent_transfers"] == []
        assert summary["company_stats"] == []
        assert summary["stripe_accounts"] == []
        assert summary["kpis"]["total_transfers"] == 0
        assert summary["kpis"]["net_income_month"] is None
        # time_clock.read is granted → the roster block survives.
        assert isinstance(summary["clocked_in"], list)
    finally:
        clear_user_permissions(test_store_id, uid)


# ── R-2: overlay written at creation time ───────────────────


def test_create_user_with_permissions_matrix(client, test_store_id):
    """POST /admin/users with a `permissions` matrix writes the
    overlay atomically with the account — the first login already
    carries only the custom perms."""
    from api.Core.Permissions import clear_user_permissions, user_has_custom_permissions

    token = login_admin(client, test_store_id)
    made = client.post(
        "/api/v2/admin/users", headers=_headers(token),
        json={
            "email":    "r2.amber.new@store.com",
            "password": "newpass1234",
            "full_name": "Amber",
            "role": "employee",
            "permissions": HR_ONLY,
        },
    )
    assert made.status_code == 201, made.get_data(as_text=True)
    row = made.get_json()
    assert row["has_custom_permissions"] is True
    uid = row["id"]
    try:
        assert user_has_custom_permissions(uid, test_store_id) is True
        login = client.post(
            "/api/v2/auth/login",
            json={
                "username": "r2.amber.new@store.com",
                "password": "newpass1234",
                "store_id": test_store_id,
            },
        ).get_json()
        assert "time_clock.read" in login["permissions"]
        assert "transfers.read" not in login["permissions"]
    finally:
        clear_user_permissions(test_store_id, uid)


def test_create_user_without_permissions_has_no_overlay(
    client, test_store_id,
):
    token = login_admin(client, test_store_id)
    made = client.post(
        "/api/v2/admin/users", headers=_headers(token),
        json={
            "email":    "r2.plain.new@store.com",
            "password": "newpass1234",
            "role": "employee",
        },
    )
    assert made.status_code == 201
    assert made.get_json()["has_custom_permissions"] is False
