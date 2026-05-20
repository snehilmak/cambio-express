"""HTTP integration tests for the Auth Controllers (PR 20)."""
from fastapi.testclient import TestClient
from tests._app import db, db_session
import pytest


@pytest.fixture
def api_client():
    from api.main import api_app
    with TestClient(api_app) as c:
        yield c


# ── POST /auth/login ────────────────────────────────────────


def test_login_returns_token_and_summary(test_store_id, api_client):
    resp = api_client.post(
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


def test_login_returns_401_on_bad_password(test_store_id, api_client):
    resp = api_client.post(
        "/auth/login",
        json={
            "username": "admin@test.com",
            "password": "wrong",
            "store_id": test_store_id,
        },
    )
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Invalid username or password"


def test_login_returns_401_on_unknown_user(test_store_id, api_client):
    resp = api_client.post(
        "/auth/login",
        json={
            "username": "ghost@x.com",
            "password": "x",
            "store_id": test_store_id,
        },
    )
    assert resp.status_code == 401


def test_login_finds_superadmin_with_null_store_id(api_client):
    """The seeded superadmin is pre-enrolled in TOTP (see
    tests/conftest.py's seed_test_data) so login returns a 2FA
    pending response, not a full token. enroll_required must be
    False — they're already enrolled — and the SPA exchanges the
    pending_token via /auth/login/totp to get the access token.
    Tests that need a real bearer token use the
    `login_superadmin(client)` helper from conftest."""
    resp = api_client.post(
        "/auth/login",
        json={
            "username": "superadmin",
            "password": "super2025!",
            "store_id": None,
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["requires_totp"] is True
    assert body["enroll_required"] is False
    assert body["pending_token"]
    assert body["user_id"]


def test_login_rejects_extra_fields(test_store_id, api_client):
    """Pydantic schema sets extra="forbid" — typos in the request
    body should fail loudly with 422."""
    resp = api_client.post(
        "/auth/login",
        json={
            "username": "admin@test.com",
            "password": "testpass123!",
            "store_id": test_store_id,
            "remember": True,  # not in schema
        },
    )
    assert resp.status_code == 422


def test_login_rejects_empty_username(test_store_id, api_client):
    resp = api_client.post(
        "/auth/login",
        json={"username": "", "password": "x", "store_id": test_store_id},
    )
    assert resp.status_code == 422


# ── GET /auth/me ────────────────────────────────────────────


def test_me_returns_principal_for_valid_token(test_store_id, api_client):
    c = api_client
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


def test_me_rejects_missing_authorization_header(api_client):
    resp = api_client.get("/auth/me")
    assert resp.status_code == 401
    assert resp.headers.get("www-authenticate") == "Bearer"


def test_me_rejects_non_bearer_authorization(api_client):
    resp = api_client.get(
        "/auth/me", headers={"Authorization": "Basic abc"},
    )
    assert resp.status_code == 401


def test_me_rejects_empty_bearer_token(api_client):
    resp = api_client.get(
        "/auth/me", headers={"Authorization": "Bearer "},
    )
    assert resp.status_code == 401


def test_me_rejects_tampered_token(test_store_id, api_client):
    c = api_client
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


def test_me_rejects_garbage_token(api_client):
    resp = api_client.get(
        "/auth/me", headers={"Authorization": "Bearer not-a-real-jwt"},
    )
    assert resp.status_code == 401


# ── Cookie-based JWT (PR #559) ──────────────────────────────


def test_login_sets_httponly_access_token_cookie(test_store_id, api_client):
    """Successful login drops the JWT into a httpOnly cookie
    alongside the body's ``access_token`` field. The SPA reads the
    cookie (browsers attach it automatically); curl / scripts /
    tests keep using the body field."""
    resp = api_client.post(
        "/auth/login",
        json={
            "username": "admin@test.com",
            "password": "testpass123!",
            "store_id": test_store_id,
        },
    )
    assert resp.status_code == 200
    set_cookie = resp.headers.get_list("set-cookie")
    matching = [c for c in set_cookie if c.startswith("db_access_token=")]
    assert matching, f"expected db_access_token cookie; got {set_cookie!r}"
    cookie = matching[0]
    # httpOnly so XSS can't read the token via document.cookie.
    assert "HttpOnly" in cookie
    # SameSite=Lax — Stripe / SSO redirects need top-level GETs to
    # carry the cookie, but cross-origin embedded requests don't.
    assert "SameSite=lax" in cookie or "SameSite=Lax" in cookie
    # Body still carries the token for non-SPA callers.
    body = resp.json()
    assert body["access_token"]
    # And the cookie value matches what's in the body.
    cookie_value = cookie.split(";", 1)[0].split("=", 1)[1]
    assert cookie_value == body["access_token"]


def test_get_principal_accepts_cookie_when_no_header(test_store_id, api_client):
    """A logged-in client doesn't need to send Authorization
    explicitly — the cookie jar attaches db_access_token and
    /auth/me succeeds. This is the SPA's post-PR-#559 path."""
    api_client.post(
        "/auth/login",
        json={
            "username": "admin@test.com",
            "password": "testpass123!",
            "store_id": test_store_id,
        },
    )
    # No Authorization header — cookie alone.
    resp = api_client.get("/auth/me")
    assert resp.status_code == 200
    assert resp.json()["role"] == "admin"


def test_logout_clears_access_token_cookie(test_store_id, api_client):
    """``POST /auth/logout`` returns 204 and sets a Set-Cookie
    header that deletes ``db_access_token`` (Max-Age=0 / past
    Expires). Subsequent calls without an Authorization header
    return 401."""
    api_client.post(
        "/auth/login",
        json={
            "username": "admin@test.com",
            "password": "testpass123!",
            "store_id": test_store_id,
        },
    )
    resp = api_client.post("/auth/logout")
    assert resp.status_code == 204
    set_cookie = resp.headers.get_list("set-cookie")
    clears = [c for c in set_cookie if c.startswith("db_access_token=")]
    assert clears, f"expected db_access_token clear; got {set_cookie!r}"
    # The clear directive uses Max-Age=0 or an Expires in the past.
    clear = clears[0]
    assert "Max-Age=0" in clear or "1970" in clear or "GMT" in clear
    # And /auth/me now bounces without auth.
    me = api_client.get("/auth/me")
    assert me.status_code == 401


# ── Refresh tokens (PR #560) ────────────────────────────────


def test_login_sets_refresh_token_cookie(test_store_id, client):
    """Every login path drops a separate ``db_refresh_token``
    httpOnly cookie scoped to ``/api/v2/auth``. SPA uses it to
    silently rotate the access JWT on expiry. We use the conftest
    ``client`` (full asgi_app, sees ``/api/v2/...`` paths) so the
    cookie's ``Path=/api/v2/auth`` actually matches subsequent
    refresh hits."""
    resp = client.post(
        "/api/v2/auth/login",
        json={
            "username": "admin@test.com",
            "password": "testpass123!",
            "store_id": test_store_id,
        },
    )
    assert resp.status_code == 200
    set_cookie = resp.headers.get_list("set-cookie")
    matching = [c for c in set_cookie if c.startswith("db_refresh_token=")]
    assert matching, f"expected db_refresh_token cookie; got {set_cookie!r}"
    cookie = matching[0]
    assert "HttpOnly" in cookie
    assert "Path=/api/v2/auth" in cookie


def test_refresh_rotates_access_and_refresh_cookies(
    test_store_id, client,
):
    """Successful refresh issues a brand-new access cookie + a
    brand-new refresh cookie. Refresh-token jti rotates (the
    legitimate test of "rotation happened" — the access JWT
    might be byte-identical to the login one if both issuances
    fall in the same wall-clock second, since HS256 + same
    payload is deterministic)."""
    from tests.conftest import _starlette_client
    login = client.post(
        "/api/v2/auth/login",
        json={
            "username": "admin@test.com",
            "password": "testpass123!",
            "store_id": test_store_id,
        },
    )
    assert login.status_code == 200
    old_refresh_jti = _starlette_client.cookies.get("db_refresh_token")
    assert old_refresh_jti

    refresh = client.post("/api/v2/auth/refresh")
    assert refresh.status_code == 200, refresh.get_data(as_text=True)
    new_cookies = refresh.headers.get_list("set-cookie")
    assert any(c.startswith("db_access_token=") for c in new_cookies)
    assert any(c.startswith("db_refresh_token=") for c in new_cookies)
    # Rotation: the cookie jar now holds a NEW jti.
    new_refresh_jti = _starlette_client.cookies.get("db_refresh_token")
    assert new_refresh_jti
    assert new_refresh_jti != old_refresh_jti
    # Identity claims surface in the body so the SPA can update
    # its local cache without a separate /auth/me roundtrip.
    body = refresh.get_json()
    assert body["role"] == "admin"
    assert body["store_id"] == test_store_id
    assert body["username"] == "admin@test.com"


def test_refresh_replay_burns_the_chain(test_store_id, client):
    """Presenting the same refresh token twice — second call is a
    replay. Server rejects, clears cookies."""
    client.post(
        "/api/v2/auth/login",
        json={
            "username": "admin@test.com",
            "password": "testpass123!",
            "store_id": test_store_id,
        },
    )
    from tests.conftest import _starlette_client
    first_jti = _starlette_client.cookies.get("db_refresh_token")
    assert first_jti

    rot1 = client.post("/api/v2/auth/refresh")
    assert rot1.status_code == 200

    # Replay the original jti directly via the session client.
    # `_starlette_client.cookies.set(...)` (rather than the
    # per-request `cookies=` kwarg httpx is deprecating) puts the
    # cookie on the client jar; the conftest cookie-clear between
    # tests handles cleanup.
    _starlette_client.cookies.set("db_refresh_token", first_jti)
    replay = _starlette_client.post("/api/v2/auth/refresh")
    assert replay.status_code == 401, replay.text


def test_refresh_without_cookie_returns_401(client):
    resp = client.post("/api/v2/auth/refresh")
    assert resp.status_code == 401


def test_logout_revokes_refresh_token(test_store_id, client):
    """Logout clears both cookies AND marks the refresh row
    revoked, so a subsequent refresh with the same jti fails
    even if the cookie were replayed."""
    client.post(
        "/api/v2/auth/login",
        json={
            "username": "admin@test.com",
            "password": "testpass123!",
            "store_id": test_store_id,
        },
    )
    from tests.conftest import _starlette_client
    captured_jti = _starlette_client.cookies.get("db_refresh_token")
    assert captured_jti

    logout = client.post("/api/v2/auth/logout")
    assert logout.status_code == 204
    clears = logout.headers.get_list("set-cookie")
    assert any(c.startswith("db_access_token=") for c in clears)
    assert any(c.startswith("db_refresh_token=") for c in clears)

    # See test_refresh_replay_burns_the_chain above for the
    # cookies-on-client pattern (avoids the httpx deprecation
    # warning on the per-request cookies kwarg).
    _starlette_client.cookies.set("db_refresh_token", captured_jti)
    replay = _starlette_client.post("/api/v2/auth/refresh")
    assert replay.status_code == 401


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


def test_openapi_includes_auth_paths(api_client):
    resp = api_client.get("/openapi.json")
    assert resp.status_code == 200
    paths = set(resp.json()["paths"].keys())
    assert "/auth/login" in paths
    assert "/auth/me" in paths
    assert "/auth/login-cross-store" in paths


# ── GET /auth/store-by-slug/{slug} ──────────────────────────


def test_store_by_slug_returns_public_fields(client, test_store_id):  # noqa: ARG001
    """Public lookup so the SPA's per-store login page can render
    the store name in its branding pane before the user signs in."""
    resp = client.get("/api/v2/auth/store-by-slug/test-store")
    assert resp.status_code == 200
    body = resp.get_json()
    # extra="forbid" — only public fields, no plan / Stripe IDs.
    assert set(body.keys()) == {"store_id", "name", "slug"}
    assert body["name"] == "Test Store"
    assert body["slug"] == "test-store"


def test_store_by_slug_404_unknown(client):
    resp = client.get("/api/v2/auth/store-by-slug/no-such-store")
    assert resp.status_code == 404


def test_store_by_slug_404_inactive(client, test_store_id):
    """Inactive stores return 404 — no leak that the slug exists."""
    from api.Modules.Tenancy.Models import Store
    from tests._app import db
    with db_session():
        s = db.session.get(Store, test_store_id)
        s.is_active = False
        db.session.commit()
    resp = client.get("/api/v2/auth/store-by-slug/test-store")
    assert resp.status_code == 404


def test_store_by_slug_lowercases_input(client, test_store_id):  # noqa: ARG001
    """Lookup is case-insensitive on the input slug — uppercase
    URL still resolves so we don't 404 PWA users typing the
    address-bar form of their store."""
    resp = client.get("/api/v2/auth/store-by-slug/TEST-STORE")
    assert resp.status_code == 200


# ── POST /auth/login (per-store cookie + LoginEvent) ────────


def test_login_with_store_id_sets_last_store_cookie(client, test_store_id):
    """When the body carries a store_id we set the legacy
    `ds_last_store` cookie so the installed-PWA bounce path on
    `/` still works after migration."""
    resp = client.post("/api/v2/auth/login", json={
        "username": "admin@test.com",
        "password": "testpass123!",
        "store_id": test_store_id,
    })
    assert resp.status_code == 200
    cookies = resp.headers.get_list("Set-Cookie")
    assert any("ds_last_store=test-store" in c for c in cookies), \
        f"expected ds_last_store cookie, got {cookies!r}"


def test_login_records_login_event(client, test_store_id, test_admin_id):
    """SPA logins record a LoginEvent so DAU/MAU stays accurate
    after the migration (legacy /login Flask route did this via
    `_record_login`; the FastAPI port mirrors it)."""
    from api.Modules.Auth.Models import LoginEvent
    with db_session():
        before = db.session.query(LoginEvent).filter_by(user_id=test_admin_id).count()
    client.post("/api/v2/auth/login", json={
        "username": "admin@test.com",
        "password": "testpass123!",
        "store_id": test_store_id,
    })
    with db_session():
        after = db.session.query(LoginEvent).filter_by(user_id=test_admin_id).count()
    assert after == before + 1


# ── POST /auth/login-cross-store ────────────────────────────
#
# The SPA's generic landing page doesn't know which store a user
# belongs to. This endpoint accepts username + password and looks
# up the user's home store across every store. Mirrors the legacy
# Flask `/login` POST behavior including the employee rejection.


def test_cross_store_login_admin_finds_store_and_returns_token(test_store_id, api_client):
    """An admin signing in from the cookieless landing page gets
    a JWT scoped to their home store, even though the request body
    didn't carry `store_id`."""
    resp = api_client.post(
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


def test_cross_store_login_rejects_employee(api_client):
    """Employees must use their store's slug-scoped sign-in URL.
    The cookieless cross-store login refuses them with the same
    opaque 401 as a bad password — never leaks role info."""
    from api.Modules.Tenancy.Models import User
    from tests._app import db
    u = User(
        store_id=None, username="empx@test.com", role="employee",
        is_active=True, full_name="",
    )
    u.set_password("emppass123!")
    db.session.add(u); db.session.commit()
    try:
        resp = api_client.post(
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


def test_cross_store_login_rejects_bad_password(test_store_id, api_client):  # noqa: ARG001
    resp = api_client.post(
        "/auth/login-cross-store",
        json={"username": "admin@test.com", "password": "wrong"},
    )
    assert resp.status_code == 401


def test_cross_store_login_rejects_unknown_user(api_client):
    resp = api_client.post(
        "/auth/login-cross-store",
        json={"username": "ghost@nope.com", "password": "x"},
    )
    assert resp.status_code == 401


def test_cross_store_login_token_works_against_me(test_store_id, api_client):  # noqa: ARG001
    """The token issued by /auth/login-cross-store must validate
    against /auth/me — same JWT issuer, same signature, same
    claim shape as /auth/login."""
    c = api_client
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


# ── POST /auth/change-password ──────────────────────────────


def test_change_password_happy_path(client, test_store_id):
    """End-to-end: log in, change password, log in with the new
    one, verify the old one fails."""
    login = client.post(
        "/api/v2/auth/login",
        json={
            "username": "admin@test.com",
            "password": "testpass123!",
            "store_id": test_store_id,
        },
    )
    token = login.get_json()["access_token"]

    cp = client.post(
        "/api/v2/auth/change-password",
        json={
            "current_password": "testpass123!",
            "new_password":     "newpass45678",
            "confirm_password": "newpass45678",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert cp.status_code == 200
    assert cp.get_json() == {"status": "ok"}

    login2 = client.post(
        "/api/v2/auth/login",
        json={
            "username": "admin@test.com",
            "password": "newpass45678",
            "store_id": test_store_id,
        },
    )
    assert login2.status_code == 200

    fail = client.post(
        "/api/v2/auth/login",
        json={
            "username": "admin@test.com",
            "password": "testpass123!",
            "store_id": test_store_id,
        },
    )
    assert fail.status_code == 401

    # Restore the password so the next test in the suite finds
    # the seeded credential.
    cp_back = client.post(
        "/api/v2/auth/change-password",
        json={
            "current_password": "newpass45678",
            "new_password":     "testpass123!",
            "confirm_password": "testpass123!",
        },
        headers={
            "Authorization":
                f"Bearer {login2.get_json()['access_token']}",
        },
    )
    assert cp_back.status_code == 200


def test_change_password_rejects_bad_current(client, test_store_id):
    login = client.post(
        "/api/v2/auth/login",
        json={
            "username": "admin@test.com",
            "password": "testpass123!",
            "store_id": test_store_id,
        },
    )
    token = login.get_json()["access_token"]
    resp = client.post(
        "/api/v2/auth/change-password",
        json={
            "current_password": "wrong-old",
            "new_password":     "newpass45678",
            "confirm_password": "newpass45678",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422
    body = resp.get_json()
    assert body["detail"]["field"] == "current_password"


def test_change_password_rejects_short(client, test_store_id):
    login = client.post(
        "/api/v2/auth/login",
        json={
            "username": "admin@test.com",
            "password": "testpass123!",
            "store_id": test_store_id,
        },
    )
    token = login.get_json()["access_token"]
    resp = client.post(
        "/api/v2/auth/change-password",
        json={
            "current_password": "testpass123!",
            "new_password":     "short",
            "confirm_password": "short",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422
    assert resp.get_json()["detail"]["field"] == "new_password"


def test_change_password_rejects_mismatch(client, test_store_id):
    login = client.post(
        "/api/v2/auth/login",
        json={
            "username": "admin@test.com",
            "password": "testpass123!",
            "store_id": test_store_id,
        },
    )
    token = login.get_json()["access_token"]
    resp = client.post(
        "/api/v2/auth/change-password",
        json={
            "current_password": "testpass123!",
            "new_password":     "newpass45678",
            "confirm_password": "newpass99999",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422
    assert resp.get_json()["detail"]["field"] == "confirm_password"


def test_change_password_requires_jwt(api_client):
    resp = api_client.post(
        "/auth/change-password",
        json={
            "current_password": "x",
            "new_password":     "newpass45678",
            "confirm_password": "newpass45678",
        },
    )
    assert resp.status_code == 401


# ── POST /auth/signup ───────────────────────────────────────


def test_signup_creates_store_and_returns_token(client):
    """Self-service signup creates the (Store, admin User) pair
    and returns a JWT scoped to the new store. The SPA can drop
    straight onto the dashboard."""
    resp = client.post(
        "/api/v2/auth/signup",
        json={
            "store_name": "New Cambio LLC",
            "email":      "owner@new-cambio.com",
            "password":   "newpass12345",
            "phone":      "+1-555-1234",
        },
    )
    assert resp.status_code == 201, resp.get_data(as_text=True)
    body = resp.get_json()
    assert body["access_token"]
    assert body["role"] == "admin"
    assert body["username"] == "owner@new-cambio.com"
    assert body["store_id"] is not None
    assert "store.admin" in body["permissions"]

    # The JWT is immediately usable on /auth/me.
    me = client.get(
        "/api/v2/auth/me",
        headers={"Authorization": f"Bearer {body['access_token']}"},
    )
    assert me.status_code == 200
    assert me.get_json()["username"] == "owner@new-cambio.com"


def test_signup_rejects_duplicate_email(client, test_store_id):  # noqa: ARG001
    """Existing admin email triggers a 409 with field=email so
    the SPA can highlight the input."""
    resp = client.post(
        "/api/v2/auth/signup",
        json={
            "store_name": "Another Store",
            "email":      "admin@test.com",  # already seeded
            "password":   "newpass12345",
        },
    )
    assert resp.status_code == 409
    body = resp.get_json()
    assert body["detail"]["field"] == "email"


def test_signup_rejects_short_password(client):
    resp = client.post(
        "/api/v2/auth/signup",
        json={
            "store_name": "Short PW Store",
            "email":      "short@example.com",
            "password":   "short",  # < 8 chars
        },
    )
    assert resp.status_code == 422


def test_signup_rejects_invalid_email(client):
    resp = client.post(
        "/api/v2/auth/signup",
        json={
            "store_name": "Bad Email Store",
            "email":      "no-at-sign",  # invalid
            "password":   "validpass12345",
        },
    )
    assert resp.status_code == 422
    body = resp.get_json()
    assert body["detail"]["field"] == "email"


def test_signup_normalizes_email(client):
    """Email + store name get stripped + email lowered. A second
    signup with mixed case on the same email collides."""
    r1 = client.post(
        "/api/v2/auth/signup",
        json={
            "store_name": "  Spaced Store  ",
            "email":      "MixedCase@Example.COM",
            "password":   "validpass12345",
        },
    )
    assert r1.status_code == 201
    assert r1.get_json()["username"] == "mixedcase@example.com"

    # Same email re-cased → 409.
    r2 = client.post(
        "/api/v2/auth/signup",
        json={
            "store_name": "Different Store",
            "email":      "mixedcase@example.com",
            "password":   "validpass12345",
        },
    )
    assert r2.status_code == 409


def test_signup_rejects_extra_fields(client):
    """Schema is extra=forbid — slug / plan etc. must not be writable."""
    resp = client.post(
        "/api/v2/auth/signup",
        json={
            "store_name": "Extra",
            "email":      "extra@example.com",
            "password":   "validpass12345",
            "plan":       "pro",  # not allowed
        },
    )
    assert resp.status_code == 422


# ── POST /auth/signup/owner ────────────────────────────────


def test_owner_signup_creates_owner_and_returns_token(client):
    """Self-service owner signup creates a User with role='owner'
    and store_id=None. Returns a JWT scoped to the owner so the
    SPA drops them straight onto /owner/dashboard."""
    resp = client.post(
        "/api/v2/auth/signup/owner",
        json={
            "full_name": "Jane Owner",
            "email":     "jane@owners.com",
            "password":  "ownerpass123",
        },
    )
    assert resp.status_code == 201, resp.get_data(as_text=True)
    body = resp.get_json()
    assert body["role"] == "owner"
    assert body["store_id"] is None
    assert body["username"] == "jane@owners.com"
    assert body["full_name"] == "Jane Owner"
    assert body["access_token"]


def test_owner_signup_email_collision_with_existing_owner(client):
    """A pre-existing User with store_id=None (another owner or
    superadmin) blocks the signup with a 409."""
    # Seed via the endpoint itself.
    client.post("/api/v2/auth/signup/owner", json={
        "full_name": "First Owner", "email": "shared@example.com",
        "password": "ownerpass123",
    })
    resp = client.post("/api/v2/auth/signup/owner", json={
        "full_name": "Second Owner", "email": "shared@example.com",
        "password": "anotherpass123",
    })
    assert resp.status_code == 409
    assert resp.get_json()["detail"]["field"] == "email"


def test_owner_signup_email_collision_with_store_admin(client, test_store_id):  # noqa: ARG001
    """An admin email already in use can't be reused as an owner —
    the legacy /signup/owner check did this, and the FastAPI port
    keeps the same predicate so login routing stays unambiguous."""
    resp = client.post("/api/v2/auth/signup/owner", json={
        "full_name": "Owner",
        "email":     "admin@test.com",  # seeded admin from conftest
        "password":  "ownerpass123",
    })
    assert resp.status_code == 409
    assert resp.get_json()["detail"]["field"] == "email"


def test_owner_signup_invalid_email_rejected(client):
    resp = client.post("/api/v2/auth/signup/owner", json={
        "full_name": "Owner", "email": "notanemail",
        "password": "ownerpass123",
    })
    assert resp.status_code == 422
    assert resp.get_json()["detail"]["field"] == "email"


def test_owner_signup_short_password_rejected(client):
    resp = client.post("/api/v2/auth/signup/owner", json={
        "full_name": "Owner", "email": "owner@short.com",
        "password": "tiny",  # < 8 chars → Pydantic 422
    })
    assert resp.status_code == 422


def test_owner_signup_rejects_extra_fields(client):
    resp = client.post("/api/v2/auth/signup/owner", json={
        "full_name": "Owner", "email": "owner@extra.com",
        "password": "ownerpass123",
        "store_id":  42,  # extra=forbid
    })
    assert resp.status_code == 422


def test_owner_signup_token_works_on_me_endpoint(client):
    """The JWT issued at signup is immediately usable — covers the
    end-to-end SPA flow."""
    resp = client.post("/api/v2/auth/signup/owner", json={
        "full_name": "Jane",
        "email":     "jane@usable.com",
        "password":  "ownerpass123",
    })
    token = resp.get_json()["access_token"]
    me = client.get(
        "/api/v2/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert me.status_code == 200
    assert me.get_json()["role"] == "owner"


# ── POST /auth/forgot-password ─ /auth/reset-password ──────


def test_forgot_password_always_returns_ok_for_unknown_email(client):
    """Unknown emails MUST silently no-op — never reveal whether
    a given address is registered (CLAUDE.md security invariant)."""
    resp = client.post(
        "/api/v2/auth/forgot-password",
        json={"email": "ghost@nope.com"},
    )
    assert resp.status_code == 200
    assert resp.get_json() == {"status": "ok"}


def test_forgot_password_issues_token_for_known_user(client, test_store_id):  # noqa: ARG001
    """Known-good email mints a PasswordResetToken row that the
    legacy SMTP delivery path can pick up."""
    from api.Modules.Auth.Models import PasswordResetToken
    from tests._app import db
    resp = client.post(
        "/api/v2/auth/forgot-password",
        json={"email": "admin@test.com"},
    )
    assert resp.status_code == 200
    with db_session():
        tokens = (
            db.session.query(PasswordResetToken)
              .filter_by(used_at=None)
              .all()
        )
        assert len(tokens) >= 1


def test_forgot_password_response_does_not_leak_token(client, test_store_id):  # noqa: ARG001
    """Response body must never include the raw token. The legacy
    contract is `{"status": "ok"}` and that's it."""
    resp = client.post(
        "/api/v2/auth/forgot-password",
        json={"email": "admin@test.com"},
    )
    body = resp.get_json()
    assert "token" not in str(body).lower()
    assert "raw" not in str(body).lower()


def test_reset_password_round_trip(client, test_store_id):
    """Issue a token via the Service helper, then consume it via
    the endpoint, then log in with the new password."""
    from tests._app import db
    from api.Modules.Auth.Services import issue_password_reset_token
    with db_session():
        issued = issue_password_reset_token(db.session, "admin@test.com")
        db.session.commit()
        raw = issued.raw_token

    resp = client.post(
        "/api/v2/auth/reset-password",
        json={
            "token": raw,
            "new_password":     "freshpass789",
            "confirm_password": "freshpass789",
        },
    )
    assert resp.status_code == 200, resp.get_data(as_text=True)
    assert resp.get_json() == {"status": "ok"}

    # Old password rejected.
    bad = client.post(
        "/api/v2/auth/login",
        json={
            "username": "admin@test.com",
            "password": "testpass123!",
            "store_id": test_store_id,
        },
    )
    assert bad.status_code == 401

    # New password works.
    good = client.post(
        "/api/v2/auth/login",
        json={
            "username": "admin@test.com",
            "password": "freshpass789",
            "store_id": test_store_id,
        },
    )
    assert good.status_code == 200


def test_reset_password_rejects_invalid_token(client):
    resp = client.post(
        "/api/v2/auth/reset-password",
        json={
            "token": "not-a-real-token",
            "new_password":     "newpass45678",
            "confirm_password": "newpass45678",
        },
    )
    assert resp.status_code == 400


def test_reset_password_rejects_expired_token(client, test_store_id):  # noqa: ARG001
    """Tokens past expires_at should 400 even if otherwise valid."""
    from api.Modules.Auth.Models import PasswordResetToken
    from tests._app import db
    from api.Modules.Auth.Services import issue_password_reset_token
    from datetime import datetime, timedelta
    with db_session():
        issued = issue_password_reset_token(db.session, "admin@test.com")
        db.session.commit()
        raw = issued.raw_token
        # Manually expire it.
        row = (
            db.session.query(PasswordResetToken)
              .filter_by(user_id=issued.user.id, used_at=None)
              .first()
        )
        row.expires_at = datetime.utcnow() - timedelta(hours=1)
        db.session.commit()

    resp = client.post(
        "/api/v2/auth/reset-password",
        json={
            "token": raw,
            "new_password":     "newpass45678",
            "confirm_password": "newpass45678",
        },
    )
    assert resp.status_code == 400


def test_reset_password_rejects_mismatched_confirm(client):
    """Even with a valid-shaped token, mismatched confirm → 422
    BEFORE we hit the DB. Defense against typos."""
    resp = client.post(
        "/api/v2/auth/reset-password",
        json={
            "token": "doesnt-matter",
            "new_password":     "passwordA12",
            "confirm_password": "passwordB12",
        },
    )
    assert resp.status_code == 422
    body = resp.get_json()
    assert body["detail"]["field"] == "confirm_password"


def test_reset_password_rejects_short_new_password(client):
    resp = client.post(
        "/api/v2/auth/reset-password",
        json={
            "token": "x",
            "new_password":     "short",
            "confirm_password": "short",
        },
    )
    assert resp.status_code == 422


def test_reset_password_consumed_token_cannot_be_reused(client, test_store_id):  # noqa: ARG001
    """One-time use enforced — second consume of the same token
    returns 400."""
    from tests._app import db
    from api.Modules.Auth.Services import issue_password_reset_token
    with db_session():
        issued = issue_password_reset_token(db.session, "admin@test.com")
        db.session.commit()
        raw = issued.raw_token

    r1 = client.post(
        "/api/v2/auth/reset-password",
        json={
            "token": raw,
            "new_password":     "firstpass11",
            "confirm_password": "firstpass11",
        },
    )
    assert r1.status_code == 200

    r2 = client.post(
        "/api/v2/auth/reset-password",
        json={
            "token": raw,
            "new_password":     "secondpass11",
            "confirm_password": "secondpass11",
        },
    )
    assert r2.status_code == 400


# ── GET /auth/referral/{code} + signup ref_code resolution ──
#
# The referral preview endpoint powers the green "$X off your
# first paid month" banner on the SPA's /signup page (see
# CLAUDE.md invariant #12). Signup itself takes an optional
# ref_code field — valid codes are resolved into a
# referred_by_code_id; unknown codes are silently dropped to
# match the legacy Jinja behavior.


def _seed_referral_code(*, owner_store_id, code="ABCD1234",
                        reward_referee_cents=5000):
    """Mint a ReferralCode row directly. Use a uniqueness-friendly
    code per test so parallel runs don't collide on the
    `code` unique index."""
    from api.Modules.Billing.Models import ReferralCode
    from tests._app import db
    rc = ReferralCode(
        owner_store_id=owner_store_id, code=code,
        reward_self_cents=10000,
        reward_referee_cents=reward_referee_cents,
        is_active=True,
    )
    db.session.add(rc); db.session.commit()
    return rc


def test_referral_preview_returns_code_and_reward(
    client, test_store_id,
):
    with db_session():
        _seed_referral_code(
            owner_store_id=test_store_id, code="GOOD1234",
            reward_referee_cents=7500,
        )
    resp = client.get("/api/v2/auth/referral/GOOD1234")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["code"] == "GOOD1234"
    assert body["reward_referee_cents"] == 7500


def test_referral_preview_404_for_unknown_code(client):
    resp = client.get("/api/v2/auth/referral/NEVERMINTED")
    assert resp.status_code == 404


def test_referral_preview_normalizes_lowercase(
    client, test_store_id,
):
    """Codes are stored uppercase; the SPA shouldn't have to
    pre-normalize. Lowercase lookup must still resolve."""
    with db_session():
        _seed_referral_code(
            owner_store_id=test_store_id, code="MIXED999",
        )
    resp = client.get("/api/v2/auth/referral/mixed999")
    assert resp.status_code == 200
    assert resp.get_json()["code"] == "MIXED999"


def test_referral_preview_strips_whitespace(client, test_store_id):
    """Pasted codes often pick up trailing whitespace; the
    endpoint must tolerate it."""
    with db_session():
        _seed_referral_code(
            owner_store_id=test_store_id, code="WHITES12",
        )
    resp = client.get("/api/v2/auth/referral/   whites12  ")
    assert resp.status_code == 200


def test_referral_preview_404_for_blank_code(client):
    """A non-empty path segment is required by FastAPI's router,
    but a whitespace-only segment should still 404 (lookup
    returns None)."""
    resp = client.get("/api/v2/auth/referral/%20")
    assert resp.status_code == 404


def test_signup_with_valid_ref_code_records_referrer(
    client, test_store_id,
):
    """When a signup carries a recognized ref_code, the new store's
    referred_by_code_id must point at the referrer's
    ReferralCode.id."""
    from api.Modules.Tenancy.Models import Store
    from tests._app import db
    with db_session():
        rc = _seed_referral_code(
            owner_store_id=test_store_id, code="REFER123",
        )
        rc_id = rc.id
    resp = client.post(
        "/api/v2/auth/signup",
        json={
            "store_name": "Referee Cambio",
            "email":      "referee@example.com",
            "password":   "validpass12345",
            "ref_code":   "REFER123",
        },
    )
    assert resp.status_code == 201
    new_store_id = resp.get_json()["store_id"]
    with db_session():
        s = db.session.get(Store, new_store_id)
        assert s.referred_by_code_id == rc_id


def test_signup_with_unknown_ref_code_silently_drops(client):
    """Unknown ref_codes don't fail the signup — they just don't
    record referred_by_code_id. Mirrors legacy Jinja behavior."""
    from api.Modules.Tenancy.Models import Store
    from tests._app import db
    resp = client.post(
        "/api/v2/auth/signup",
        json={
            "store_name": "No-Ref Cambio",
            "email":      "no-ref@example.com",
            "password":   "validpass12345",
            "ref_code":   "DOESNOTEXIST",
        },
    )
    assert resp.status_code == 201
    new_store_id = resp.get_json()["store_id"]
    with db_session():
        s = db.session.get(Store, new_store_id)
        assert s.referred_by_code_id is None


def test_signup_normalizes_ref_code_case_and_whitespace(
    client, test_store_id,
):
    """Ref codes get .strip().upper() before lookup — pasted
    'refer123 ' or 'Refer123' both resolve."""
    from api.Modules.Tenancy.Models import Store
    from tests._app import db
    with db_session():
        rc = _seed_referral_code(
            owner_store_id=test_store_id, code="NORMRF99",
        )
        rc_id = rc.id
    resp = client.post(
        "/api/v2/auth/signup",
        json={
            "store_name": "Norm Cambio",
            "email":      "norm@example.com",
            "password":   "validpass12345",
            "ref_code":   "  normrf99  ",
        },
    )
    assert resp.status_code == 201
    new_store_id = resp.get_json()["store_id"]
    with db_session():
        s = db.session.get(Store, new_store_id)
        assert s.referred_by_code_id == rc_id


def test_signup_with_no_ref_code_omits_referrer(client):
    """Absence of ref_code means referred_by_code_id stays null."""
    from api.Modules.Tenancy.Models import Store
    from tests._app import db
    resp = client.post(
        "/api/v2/auth/signup",
        json={
            "store_name": "Solo Cambio",
            "email":      "solo@example.com",
            "password":   "validpass12345",
        },
    )
    assert resp.status_code == 201
    new_store_id = resp.get_json()["store_id"]
    with db_session():
        s = db.session.get(Store, new_store_id)
        assert s.referred_by_code_id is None


def test_signup_with_inactive_ref_code_silently_drops(
    client, test_store_id,
):
    """An is_active=False referral code shouldn't credit the
    referrer — lookup_referral_code filters on is_active so the
    signup falls through to the no-referrer branch."""
    from api.Modules.Billing.Models import ReferralCode
    from api.Modules.Tenancy.Models import Store
    from tests._app import db
    with db_session():
        rc = _seed_referral_code(
            owner_store_id=test_store_id, code="INACT123",
        )
        rc.is_active = False
        db.session.commit()
    resp = client.post(
        "/api/v2/auth/signup",
        json={
            "store_name": "Inactive Ref Cambio",
            "email":      "inactive-ref@example.com",
            "password":   "validpass12345",
            "ref_code":   "INACT123",
        },
    )
    assert resp.status_code == 201
    new_store_id = resp.get_json()["store_id"]
    with db_session():
        s = db.session.get(Store, new_store_id)
        assert s.referred_by_code_id is None


# ── /auth/passkeys/register/begin + /finish ────────────────
#
# WebAuthn enrollment ported from the legacy Flask routes
# (/account/passkeys/register/{begin,finish}) so the SPA's
# Settings PasskeysCard can run the full registration dance.
# The challenge bridges between begin and finish via a signed
# JWT with `purpose: passkey-register` since FastAPI doesn't
# share Flask's `session` dict.


def _login_admin_token(client, store_id):
    resp = client.post(
        "/api/v2/auth/login",
        json={
            "username": "admin@test.com",
            "password": "testpass123!",
            "store_id": store_id,
        },
    )
    return resp.get_json()["access_token"]


def test_passkey_register_begin_requires_jwt(client):
    resp = client.post(
        "/api/v2/auth/passkeys/register/begin", json={},
    )
    assert resp.status_code == 401


def test_passkey_register_begin_returns_options_and_token(
    client, test_store_id,
):
    """Happy-path begin: returns the WebAuthn options JSON the
    SPA passes to navigator.credentials.create() + a register_token
    the SPA echoes back to /finish so the server can verify against
    the same challenge."""
    import json
    token = _login_admin_token(client, test_store_id)
    resp = client.post(
        "/api/v2/auth/passkeys/register/begin",
        json={}, headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert "register_token" in body
    assert body["register_token"]
    options = json.loads(body["options_json"])
    # Must include the user object + challenge so the browser
    # can build the public-key credential request.
    assert "challenge" in options
    assert "user" in options
    assert options["user"]["name"] == "admin@test.com"
    assert "rp" in options
    assert "pubKeyCredParams" in options


def test_passkey_register_finish_rejects_bad_token(
    client, test_store_id,
):
    """A garbage register_token must 400 — never succeed."""
    token = _login_admin_token(client, test_store_id)
    resp = client.post(
        "/api/v2/auth/passkeys/register/finish",
        json={
            "register_token": "garbage.not.a.jwt",
            "credential": {
                "id": "x", "rawId": "x", "type": "public-key",
                "response": {"clientDataJSON": "x",
                             "attestationObject": "x"},
            },
            "name": "Test",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 400


def test_passkey_register_finish_rejects_missing_fields(
    client, test_store_id,
):
    """The /finish endpoint requires both register_token AND
    credential — neither defaults silently."""
    token = _login_admin_token(client, test_store_id)
    r1 = client.post(
        "/api/v2/auth/passkeys/register/finish",
        json={"register_token": "anything"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r1.status_code == 400
    r2 = client.post(
        "/api/v2/auth/passkeys/register/finish",
        json={"credential": {}},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r2.status_code == 400


def test_passkey_register_finish_rejects_token_for_wrong_user(
    client, test_store_id,
):
    """Belt-and-suspenders: a register_token issued for user A
    can't be used by user B even if both have valid JWTs.
    The token's `sub` claim must match the authed user."""
    from api.Modules.Auth.Services import issue_passkey_register_token
    # Token issued for a different user_id (9999 — doesn't exist)
    foreign_token = issue_passkey_register_token(9999, "fakechallenge")
    token = _login_admin_token(client, test_store_id)
    resp = client.post(
        "/api/v2/auth/passkeys/register/finish",
        json={
            "register_token": foreign_token,
            "credential": {
                "id": "x", "rawId": "x", "type": "public-key",
                "response": {"clientDataJSON": "x",
                             "attestationObject": "x"},
            },
            "name": "Test",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 400
    assert "match" in resp.get_json()["detail"].lower()
