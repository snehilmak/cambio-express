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


def test_change_password_requires_jwt():
    resp = _client().post(
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
    from app import PasswordResetToken, db, app as flask_app
    resp = client.post(
        "/api/v2/auth/forgot-password",
        json={"email": "admin@test.com"},
    )
    assert resp.status_code == 200
    with flask_app.app_context():
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
    from app import db, app as flask_app
    from api.Modules.Auth.Services import issue_password_reset_token
    with flask_app.app_context():
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
    from app import PasswordResetToken, db, app as flask_app
    from api.Modules.Auth.Services import issue_password_reset_token
    from datetime import datetime, timedelta
    with flask_app.app_context():
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
    from app import db, app as flask_app
    from api.Modules.Auth.Services import issue_password_reset_token
    with flask_app.app_context():
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
