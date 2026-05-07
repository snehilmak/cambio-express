"""HTTP integration tests for the Auth Controllers (PR 20)."""
from fastapi.testclient import TestClient


def _client():
    from api.main import api_app
    return TestClient(api_app)


# ── POST /auth/login ────────────────────────────────────────


def test_login_returns_token_and_summary(test_store_id):
    resp = _client().post(
        "/auth/login",
        json={
            "username": "admin@test.com",
            "password": "testpass123!",
            "store_id": test_store_id,
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["access_token"]
    assert body["token_type"] == "Bearer"
    assert body["expires_in"] == 30 * 60
    assert body["role"] == "admin"
    assert body["store_id"] == test_store_id
    assert body["username"] == "admin@test.com"
    assert "store.admin" in body["permissions"]


def test_login_returns_401_on_bad_password(test_store_id):
    resp = _client().post(
        "/auth/login",
        json={
            "username": "admin@test.com",
            "password": "wrong",
            "store_id": test_store_id,
        },
    )
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Invalid username or password"


def test_login_returns_401_on_unknown_user(test_store_id):
    resp = _client().post(
        "/auth/login",
        json={
            "username": "ghost@x.com",
            "password": "x",
            "store_id": test_store_id,
        },
    )
    assert resp.status_code == 401


def test_login_finds_superadmin_with_null_store_id():
    resp = _client().post(
        "/auth/login",
        json={
            "username": "superadmin",
            "password": "super2025!",
            "store_id": None,
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["role"] == "superadmin"
    assert body["store_id"] is None
    assert "platform.admin" in body["permissions"]


def test_login_rejects_extra_fields(test_store_id):
    """Pydantic schema sets extra="forbid" — typos in the request
    body should fail loudly with 422."""
    resp = _client().post(
        "/auth/login",
        json={
            "username": "admin@test.com",
            "password": "testpass123!",
            "store_id": test_store_id,
            "remember": True,  # not in schema
        },
    )
    assert resp.status_code == 422


def test_login_rejects_empty_username(test_store_id):
    resp = _client().post(
        "/auth/login",
        json={"username": "", "password": "x", "store_id": test_store_id},
    )
    assert resp.status_code == 422


# ── GET /auth/me ────────────────────────────────────────────


def test_me_returns_principal_for_valid_token(test_store_id):
    c = _client()
    login = c.post(
        "/auth/login",
        json={
            "username": "admin@test.com",
            "password": "testpass123!",
            "store_id": test_store_id,
        },
    )
    token = login.json()["access_token"]
    resp = c.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["role"] == "admin"
    assert body["store_id"] == test_store_id
    assert body["username"] == "admin@test.com"
    assert "store.admin" in body["permissions"]


def test_me_rejects_missing_authorization_header():
    resp = _client().get("/auth/me")
    assert resp.status_code == 401
    assert resp.headers.get("www-authenticate") == "Bearer"


def test_me_rejects_non_bearer_authorization():
    resp = _client().get(
        "/auth/me", headers={"Authorization": "Basic abc"},
    )
    assert resp.status_code == 401


def test_me_rejects_empty_bearer_token():
    resp = _client().get(
        "/auth/me", headers={"Authorization": "Bearer "},
    )
    assert resp.status_code == 401


def test_me_rejects_tampered_token(test_store_id):
    c = _client()
    login = c.post(
        "/auth/login",
        json={
            "username": "admin@test.com",
            "password": "testpass123!",
            "store_id": test_store_id,
        },
    )
    token = login.json()["access_token"]
    # Replace the entire signature segment (after the second '.')
    # with a same-length all-A's string. Single-char tamper at the
    # end occasionally lands on a valid base64url padding boundary
    # and the JWT decodes cleanly — that's the flake we keep
    # regressing on. The whole-signature replacement is
    # deterministic. Fall back to all-B's on the 1-in-2^N chance
    # the genuine signature happens to be all-A's.
    head, payload, sig = token.split(".")
    fake_sig = "A" * len(sig) if sig != "A" * len(sig) else "B" * len(sig)
    tampered = f"{head}.{payload}.{fake_sig}"
    resp = c.get(
        "/auth/me", headers={"Authorization": f"Bearer {tampered}"},
    )
    assert resp.status_code == 401
    # WWW-Authenticate header surfaces the failure mode.
    assert "invalid" in resp.headers.get("www-authenticate", "").lower()


def test_me_rejects_garbage_token():
    resp = _client().get(
        "/auth/me", headers={"Authorization": "Bearer not-a-real-jwt"},
    )
    assert resp.status_code == 401


# ── Strangler-fig dispatch ──────────────────────────────────


def test_flask_dispatcher_routes_login_to_fastapi(client, test_store_id):
    resp = client.post(
        "/api/v2/auth/login",
        json={
            "username": "admin@test.com",
            "password": "testpass123!",
            "store_id": test_store_id,
        },
    )
    assert resp.status_code == 200
    assert resp.is_json
    assert resp.get_json()["role"] == "admin"


def test_openapi_includes_auth_paths():
    resp = _client().get("/openapi.json")
    assert resp.status_code == 200
    paths = set(resp.json()["paths"].keys())
    assert "/auth/login" in paths
    assert "/auth/me" in paths
    assert "/auth/login-cross-store" in paths


# ── POST /auth/login-cross-store ────────────────────────────
#
# The SPA's generic landing page doesn't know which store a user
# belongs to. This endpoint accepts username + password and looks
# up the user's home store across every store. Mirrors the legacy
# Flask `/login` POST behavior including the employee rejection.


def test_cross_store_login_admin_finds_store_and_returns_token(test_store_id):
    """An admin signing in from the cookieless landing page gets
    a JWT scoped to their home store, even though the request body
    didn't carry `store_id`."""
    resp = _client().post(
        "/auth/login-cross-store",
        json={"username": "admin@test.com", "password": "testpass123!"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["access_token"]
    assert body["role"] == "admin"
    # store_id was looked up server-side from the username — the
    # JWT carries the user's home store, NOT something the client
    # could spoof in the body.
    assert body["store_id"] == test_store_id
    assert "store.admin" in body["permissions"]


def test_cross_store_login_rejects_employee():
    """Employees must use their store's slug-scoped sign-in URL.
    The cookieless cross-store login refuses them with the same
    opaque 401 as a bad password — never leaks role info."""
    from app import User, db
    u = User(
        store_id=None, username="empx@test.com", role="employee",
        is_active=True, full_name="",
    )
    u.set_password("emppass123!")
    db.session.add(u); db.session.commit()
    try:
        resp = _client().post(
            "/auth/login-cross-store",
            json={"username": "empx@test.com", "password": "emppass123!"},
        )
        # 401 — same as bad-password. Body string differs but the
        # status code is identical, so a probe can't tell apart
        # "wrong password" vs "you're an employee".
        assert resp.status_code == 401
    finally:
        db.session.delete(u)
        db.session.commit()


def test_cross_store_login_rejects_bad_password(test_store_id):  # noqa: ARG001
    resp = _client().post(
        "/auth/login-cross-store",
        json={"username": "admin@test.com", "password": "wrong"},
    )
    assert resp.status_code == 401


def test_cross_store_login_rejects_unknown_user():
    resp = _client().post(
        "/auth/login-cross-store",
        json={"username": "ghost@nope.com", "password": "x"},
    )
    assert resp.status_code == 401


def test_cross_store_login_token_works_against_me(test_store_id):  # noqa: ARG001
    """The token issued by /auth/login-cross-store must validate
    against /auth/me — same JWT issuer, same signature, same
    claim shape as /auth/login."""
    c = _client()
    login = c.post(
        "/auth/login-cross-store",
        json={"username": "admin@test.com", "password": "testpass123!"},
    )
    assert login.status_code == 200
    token = login.json()["access_token"]

    me = c.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    body = me.json()
    assert body["username"] == "admin@test.com"
    assert body["role"] == "admin"
    assert "store.admin" in body["permissions"]
