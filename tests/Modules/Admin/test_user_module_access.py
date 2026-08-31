"""Per-user module access grants (U-3).

The admin/owner picks which optional modules a created user sees:
User.module_access NULL = every module the store has; a CSV subset
restricts. /auth/session-status intersects the store's module flags
with the user's grants; owners + superadmin are never restricted.

The seeded test store is msb_hybrid, so its module flags resolve to
{module_money_services, module_check_cashing}.
"""
from tests._app import db, db_session


def _admin_token(client_, store_id):
    resp = client_.post(
        "/api/v2/auth/login",
        json={
            "username": "admin@test.com",
            "password": "testpass123!",
            "store_id": store_id,
        },
    )
    return resp.get_json()["access_token"]


def _login_as(client_, store_id, username, password):
    resp = client_.post(
        "/api/v2/auth/login",
        json={
            "username": username, "password": password,
            "store_id": store_id,
        },
    )
    assert resp.status_code == 200, resp.get_data(as_text=True)
    return resp.get_json()["access_token"]


def _features(client_, token):
    resp = client_.get(
        "/api/v2/auth/session-status",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    return resp.get_json()["features"]


def _cleanup(username):
    from api.Modules.Tenancy.Models import User
    with db_session():
        row = db.session.query(User).filter_by(username=username).first()
        if row:
            db.session.delete(row)
            db.session.commit()


def test_create_with_grants_restricts_session_features(
    client, test_store_id,
):
    """A user created with specific grants sees only those modules
    (intersected with the store's flags); the roster row echoes
    the grant list."""
    admin = _admin_token(client, test_store_id)
    created = client.post(
        "/api/v2/admin/users",
        json={
            "email":    "u3.restricted@store.com",
            "password": "pass1234!",
            "role": "employee",
            "module_access": ["module_check_cashing"],
        },
        headers={"Authorization": f"Bearer {admin}"},
    )
    try:
        assert created.status_code == 201, created.get_data(as_text=True)
        assert created.get_json()["module_access"] == [
            "module_check_cashing",
        ]

        token = _login_as(
            client, test_store_id, "u3.restricted@store.com", "pass1234!",
        )
        assert _features(client, token) == ["module_check_cashing"]

        # The admin (NULL module_access) keeps the store's full set.
        assert _features(client, admin) == [
            "module_money_services", "module_check_cashing",
        ]
    finally:
        _cleanup("u3_restricted")


def test_create_rejects_unknown_module_key(client, test_store_id):
    admin = _admin_token(client, test_store_id)
    resp = client.post(
        "/api/v2/admin/users",
        json={
            "email":    "u3.badkey@store.com",
            "password": "pass1234!",
            "module_access": ["module_time_travel"],
        },
        headers={"Authorization": f"Bearer {admin}"},
    )
    try:
        assert resp.status_code == 422
        assert "module_time_travel" in str(resp.get_json())
    finally:
        _cleanup("u3_bad_key")


def test_patch_semantics_omitted_null_and_empty(client, test_store_id):
    """PATCH: omitted leaves grants alone; [] = none of the optional
    modules; null clears back to the store's full set."""
    admin = _admin_token(client, test_store_id)
    created = client.post(
        "/api/v2/admin/users",
        json={
            "email":    "u3.patch@store.com",
            "password": "pass1234!",
            "module_access": ["module_check_cashing"],
        },
        headers={"Authorization": f"Bearer {admin}"},
    )
    try:
        assert created.status_code == 201
        user_id = created.get_json()["id"]

        # Omitted field → grants unchanged.
        patched = client.patch(
            f"/api/v2/admin/users/{user_id}",
            json={"full_name": "Still Restricted"},
            headers={"Authorization": f"Bearer {admin}"},
        )
        assert patched.status_code == 200
        assert patched.get_json()["module_access"] == [
            "module_check_cashing",
        ]

        # Empty list → no optional modules at all.
        patched = client.patch(
            f"/api/v2/admin/users/{user_id}",
            json={"module_access": []},
            headers={"Authorization": f"Bearer {admin}"},
        )
        assert patched.status_code == 200
        assert patched.get_json()["module_access"] == []
        token = _login_as(client, test_store_id, "u3.patch@store.com", "pass1234!")
        assert _features(client, token) == []

        # Explicit null → back to every store module.
        patched = client.patch(
            f"/api/v2/admin/users/{user_id}",
            json={"module_access": None},
            headers={"Authorization": f"Bearer {admin}"},
        )
        assert patched.status_code == 200
        assert patched.get_json()["module_access"] is None
        token = _login_as(client, test_store_id, "u3.patch@store.com", "pass1234!")
        assert _features(client, token) == [
            "module_money_services", "module_check_cashing",
        ]
    finally:
        _cleanup("u3_patch")


def test_superadmin_features_never_restricted(client):
    """Superadmin has no store scope and no grants row that could
    restrict — session-status returns every module flag."""
    from tests.conftest import login_superadmin
    from api.Modules.Billing.Services.feature_flags import MODULE_FLAG_KEYS
    token = login_superadmin(client)
    assert _features(client, token) == list(MODULE_FLAG_KEYS)
