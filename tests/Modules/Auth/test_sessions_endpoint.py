"""HTTP integration tests for the active-sessions endpoints.

Three routes:

  GET    /api/v2/auth/sessions               → list
  DELETE /api/v2/auth/sessions/others        → revoke all but current
  DELETE /api/v2/auth/sessions/{session_id}  → revoke one

Auth gating: every route requires a valid JWT. The user_id +
sid claims drive who can see / revoke what.
"""
from tests._app import db, db_session


def _login(client_, store_id, *, ua: str = "TestClient/1.0"):
    """Drive the password-login flow and return ``access_token`` +
    refresh cookie. Sends a User-Agent header so the resulting
    refresh-token row has a non-empty ``user_agent``."""
    resp = client_.post(
        "/api/v2/auth/login",
        json={
            "username": "admin@test.com",
            "password": "testpass123!",
            "store_id": store_id,
        },
        headers={"User-Agent": ua},
    )
    return resp.get_json()["access_token"]


def _login_extra(client_, store_id, username, password, *, ua: str = "TestClient/Other"):
    """Log in as a different user (must be pre-seeded)."""
    resp = client_.post(
        "/api/v2/auth/login",
        json={
            "username": username,
            "password": password,
            "store_id": store_id,
        },
        headers={"User-Agent": ua},
    )
    return resp.get_json()["access_token"]


# ── Auth gating ────────────────────────────────────────────


def test_list_sessions_requires_jwt(client):
    resp = client.get("/api/v2/auth/sessions")
    assert resp.status_code == 401


def test_revoke_session_requires_jwt(client):
    resp = client.delete("/api/v2/auth/sessions/abc-123")
    assert resp.status_code == 401


def test_revoke_others_requires_jwt(client):
    resp = client.delete("/api/v2/auth/sessions/others")
    assert resp.status_code == 401


# ── /sessions list ─────────────────────────────────────────


def test_list_returns_at_least_the_current_session(
    client, test_store_id,
):
    """One ``/auth/login`` call yields one refresh row → one
    session on the panel. The current-session flag is True for
    that row."""
    token = _login(client, test_store_id, ua="Chrome on macOS")
    resp = client.get(
        "/api/v2/auth/sessions",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert len(body["sessions"]) >= 1
    current = [s for s in body["sessions"] if s["is_current"]]
    assert len(current) == 1
    assert current[0]["user_agent"] == "Chrome on macOS"


def test_list_two_logins_show_two_sessions(client, test_store_id):
    """Logging in twice as the same user (different cookies) creates
    two distinct sessions. The panel shows both; only one is current
    relative to the JWT used to query."""
    # First login (cookies + access token A)
    token_a = _login(client, test_store_id, ua="UA-A")
    # Second login wipes cookies on the same client, so we need
    # a fresh client jar. The conftest's ``client`` fixture is a
    # session-scoped Starlette TestClient — calling /auth/login
    # again sets new cookies but the OLD refresh row stays in
    # the DB (it's still active). That's exactly the "two
    # devices" state we want.
    _login(client, test_store_id, ua="UA-B")
    # Use token_a to query — its session is the OLDER one and
    # should be flagged "not current" since cookies now point at
    # the newer one. But wait: the access TOKEN carries the sid
    # claim minted at login time. token_a's sid points at its
    # session. So token_a sees itself as current.
    resp = client.get(
        "/api/v2/auth/sessions",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    body = resp.get_json()
    assert len(body["sessions"]) >= 2
    # Exactly one of the rows is marked current.
    current = [s for s in body["sessions"] if s["is_current"]]
    assert len(current) == 1


def test_list_isolates_users(client, test_store_id):
    """User A's sessions never leak into User B's list — even
    when both are logged in."""
    from api.Modules.Tenancy.Models import User
    with db_session():
        # Second admin so we have two distinct user_ids.
        u = User(
            store_id=test_store_id, username="sess-admin-b@test.com",
            full_name="Sess Admin B", role="admin",
        )
        u.set_password("pw-sess-b!")
        db.session.add(u); db.session.commit()
    token_a = _login(client, test_store_id, ua="UA-A")
    token_b = _login_extra(
        client, test_store_id,
        username="sess-admin-b@test.com", password="pw-sess-b!",
        ua="UA-B",
    )
    a_resp = client.get(
        "/api/v2/auth/sessions",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    a_session_ids = {s["session_id"] for s in a_resp.get_json()["sessions"]}
    b_resp = client.get(
        "/api/v2/auth/sessions",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    b_session_ids = {s["session_id"] for s in b_resp.get_json()["sessions"]}
    # No overlap.
    assert a_session_ids & b_session_ids == set()


# ── /sessions/{session_id} revoke ───────────────────────────


def test_revoke_session_removes_chain_from_list(
    client, test_store_id,
):
    """Revoke a non-current session and confirm it disappears
    from the panel."""
    token = _login(client, test_store_id, ua="UA-Current")
    # Force a second login so there's a non-current session to
    # revoke.
    _login(client, test_store_id, ua="UA-Other")
    list_body = client.get(
        "/api/v2/auth/sessions",
        headers={"Authorization": f"Bearer {token}"},
    ).get_json()
    non_current = [
        s for s in list_body["sessions"] if not s["is_current"]
    ]
    assert non_current, list_body
    victim_id = non_current[0]["session_id"]
    resp = client.delete(
        f"/api/v2/auth/sessions/{victim_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    after = client.get(
        "/api/v2/auth/sessions",
        headers={"Authorization": f"Bearer {token}"},
    ).get_json()
    assert all(s["session_id"] != victim_id for s in after["sessions"])


def test_revoke_session_cant_kill_other_users_session(
    client, test_store_id,
):
    """A cross-user revoke returns ``{revoked: 0}`` instead of
    404 — same shape either way so a probing caller can't
    distinguish "exists but not yours" from "doesn't exist"."""
    from api.Modules.Tenancy.Models import User
    with db_session():
        u = User(
            store_id=test_store_id, username="sess-rev-iso@test.com",
            full_name="Sess Iso", role="admin",
        )
        u.set_password("pw-iso!")
        db.session.add(u); db.session.commit()
    token_a = _login(client, test_store_id, ua="UA-A")
    token_b = _login_extra(
        client, test_store_id,
        username="sess-rev-iso@test.com", password="pw-iso!",
        ua="UA-B",
    )
    # Find A's session_id and try to revoke it as B.
    a_sessions = client.get(
        "/api/v2/auth/sessions",
        headers={"Authorization": f"Bearer {token_a}"},
    ).get_json()["sessions"]
    a_session_id = next(
        s["session_id"] for s in a_sessions if s["is_current"]
    )
    resp = client.delete(
        f"/api/v2/auth/sessions/{a_session_id}",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert resp.status_code == 200
    assert resp.get_json()["revoked"] == 0
    # A's session is still alive.
    a_after = client.get(
        "/api/v2/auth/sessions",
        headers={"Authorization": f"Bearer {token_a}"},
    ).get_json()
    assert any(
        s["session_id"] == a_session_id for s in a_after["sessions"]
    )


# ── /sessions/others ───────────────────────────────────────


def test_revoke_others_keeps_current_session(
    client, test_store_id,
):
    """Two logins → one current + one stale. Calling
    ``/sessions/others`` with the current JWT revokes the stale
    one; the panel ends up with just the current row."""
    token = _login(client, test_store_id, ua="UA-Current")
    _login(client, test_store_id, ua="UA-Stale")
    resp = client.delete(
        "/api/v2/auth/sessions/others",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    after = client.get(
        "/api/v2/auth/sessions",
        headers={"Authorization": f"Bearer {token}"},
    ).get_json()
    # Only the current session remains.
    assert len(after["sessions"]) == 1
    assert after["sessions"][0]["is_current"] is True


def test_revoke_others_isolates_users(client, test_store_id):
    """User B running ``/sessions/others`` does NOT touch User A's
    sessions."""
    from api.Modules.Tenancy.Models import User
    with db_session():
        u = User(
            store_id=test_store_id, username="sess-others-iso@test.com",
            full_name="Sess Others Iso", role="admin",
        )
        u.set_password("pw-others-iso!")
        db.session.add(u); db.session.commit()
    token_a = _login(client, test_store_id, ua="UA-A")
    token_b = _login_extra(
        client, test_store_id,
        username="sess-others-iso@test.com", password="pw-others-iso!",
        ua="UA-B",
    )
    client.delete(
        "/api/v2/auth/sessions/others",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    # A's sessions are untouched.
    a_after = client.get(
        "/api/v2/auth/sessions",
        headers={"Authorization": f"Bearer {token_a}"},
    ).get_json()
    assert len(a_after["sessions"]) >= 1


# ── JWT carries the session_id claim ────────────────────────


def test_login_embeds_sid_claim_in_access_token(client, test_store_id):
    """The new ``sid`` claim makes the sessions panel's
    ``is_current`` flag possible without an extra DB lookup per
    request — pin the contract."""
    import jwt as _jwt

    token = _login(client, test_store_id, ua="JWT-test")
    claims = _jwt.decode(token, options={"verify_signature": False})
    assert "sid" in claims
    assert isinstance(claims["sid"], str)
    assert len(claims["sid"]) > 0
