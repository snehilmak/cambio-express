"""HTTP integration tests for the SPA 2FA login flow.

After SPA-31 the /auth/login (and /auth/login-cross-store) routes
return a `requires_totp=True` envelope with a short-lived pending
token instead of an access token whenever the user is in a
TOTP-required role AND has actually enrolled. The pending token
is then exchanged via /auth/login/totp or /auth/login/recovery.

Users who SHOULD use 2FA but haven't enrolled fall through to the
full login (transitional behavior — enrollment lives on the
legacy site for now).

These tests deliberately create their own ephemeral superadmin
users instead of mutating the seeded `superadmin` row. Mutating
shared seed state can leak across tests via SA's identity map
even with the per-test `db.drop_all()` / `db.create_all()` cycle
in conftest, and that's how PR #347's first CI run flaked the
unrelated `test_line_items_delete_round_trip` setup.
"""
from datetime import datetime

import pyotp


def _make_enrolled_superadmin(*, slug="ts2fa"):
    """Create a brand-new superadmin User with TOTP enrolled.
    Returns (username, password, totp_secret). Each test gets its
    own row so we don't mutate the shared seeded `superadmin`."""
    from app import User, db
    secret = pyotp.random_base32()
    username = f"{slug}@superadmin"
    user = User(
        store_id=None, username=username,
        full_name="Test Super", role="superadmin",
        totp_secret=secret, totp_enrolled_at=datetime.utcnow(),
    )
    user.set_password("super2025!")
    db.session.add(user); db.session.commit()
    return username, "super2025!", secret


def _add_recovery_code(username, raw_code="ABCD1234"):
    """Stash a single recovery code for the given ephemeral
    superadmin (created by `_make_enrolled_superadmin`)."""
    from app import RecoveryCode, User, db
    from api.Modules.Auth.Services.totp import hash_recovery_code
    sa = User.query.filter_by(username=username).first()
    db.session.add(RecoveryCode(
        user_id=sa.id, code_hash=hash_recovery_code(raw_code),
    ))
    db.session.commit()


# ── Pending-token issuance ──────────────────────────────────


def test_login_returns_pending_when_superadmin_enrolled(client):
    from app import app as flask_app
    with flask_app.app_context():
        username, password, _ = _make_enrolled_superadmin(slug="t1")
    resp = client.post(
        "/api/v2/auth/login",
        json={"username": username, "password": password, "store_id": None},
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["requires_totp"] is True
    assert body["pending_token"]
    assert body["access_token"] == ""
    assert body["has_recovery_codes"] is False


def test_login_with_recovery_code_flag(client):
    from app import app as flask_app
    with flask_app.app_context():
        username, password, _ = _make_enrolled_superadmin(slug="t2")
        _add_recovery_code(username)
    resp = client.post(
        "/api/v2/auth/login",
        json={"username": username, "password": password, "store_id": None},
    )
    body = resp.get_json()
    assert body["requires_totp"] is True
    assert body["has_recovery_codes"] is True


def test_login_unenrolled_superadmin_falls_through(client):
    """Until SPA enrollment ships, an unenrolled superadmin gets a
    full token. (Production superadmins should always be enrolled
    via the legacy /login/2fa/enroll flow before they hit the
    SPA.)"""
    resp = client.post(
        "/api/v2/auth/login",
        json={
            "username": "superadmin", "password": "super2025!",
            "store_id": None,
        },
    )
    body = resp.get_json()
    assert body["requires_totp"] is False
    assert body["access_token"]


def test_admin_login_unaffected_by_2fa_flow(client, test_store_id):
    """Admin role isn't in _TOTP_REQUIRED_ROLES, so no 2FA hop
    regardless of TOTP secret state."""
    resp = client.post(
        "/api/v2/auth/login",
        json={
            "username": "admin@test.com",
            "password": "testpass123!",
            "store_id": test_store_id,
        },
    )
    body = resp.get_json()
    assert body["requires_totp"] is False
    assert body["access_token"]


# ── /auth/login/totp ────────────────────────────────────────


def test_login_totp_exchanges_pending_for_access_token(client):
    from app import app as flask_app
    with flask_app.app_context():
        username, password, secret = _make_enrolled_superadmin(slug="t3")
    pending = client.post(
        "/api/v2/auth/login",
        json={"username": username, "password": password, "store_id": None},
    ).get_json()["pending_token"]
    code = pyotp.TOTP(secret).now()
    resp = client.post(
        "/api/v2/auth/login/totp",
        json={"pending_token": pending, "code": code},
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["access_token"]
    assert body["role"] == "superadmin"
    assert body["requires_totp"] is False


def test_login_totp_rejects_bad_code(client):
    from app import app as flask_app
    with flask_app.app_context():
        username, password, _ = _make_enrolled_superadmin(slug="t4")
    pending = client.post(
        "/api/v2/auth/login",
        json={"username": username, "password": password, "store_id": None},
    ).get_json()["pending_token"]
    resp = client.post(
        "/api/v2/auth/login/totp",
        json={"pending_token": pending, "code": "000000"},
    )
    assert resp.status_code == 401


def test_login_totp_rejects_garbage_pending_token(client):
    resp = client.post(
        "/api/v2/auth/login/totp",
        json={"pending_token": "not.a.jwt", "code": "123456"},
    )
    assert resp.status_code == 401


def test_login_totp_rejects_access_token_used_as_pending(client, test_store_id):
    """An ordinary access token (no purpose claim) must NOT be
    accepted by the /totp exchange — the purpose check rejects it."""
    body = client.post(
        "/api/v2/auth/login",
        json={
            "username": "admin@test.com",
            "password": "testpass123!",
            "store_id": test_store_id,
        },
    ).get_json()
    access_token = body["access_token"]
    assert access_token  # confirm setup
    resp = client.post(
        "/api/v2/auth/login/totp",
        json={"pending_token": access_token, "code": "123456"},
    )
    assert resp.status_code == 401


# ── /auth/login/recovery ────────────────────────────────────


def test_login_recovery_consumes_code_and_issues_token(client):
    from app import app as flask_app, RecoveryCode
    with flask_app.app_context():
        username, password, _ = _make_enrolled_superadmin(slug="t5")
        _add_recovery_code(username, "WXYZ7890")
        before = RecoveryCode.query.filter_by(used_at=None).count()
    pending = client.post(
        "/api/v2/auth/login",
        json={"username": username, "password": password, "store_id": None},
    ).get_json()["pending_token"]
    resp = client.post(
        "/api/v2/auth/login/recovery",
        json={"pending_token": pending, "code": "WXYZ-7890"},
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["access_token"]
    assert body["role"] == "superadmin"
    with flask_app.app_context():
        after = RecoveryCode.query.filter_by(used_at=None).count()
    assert after == before - 1


def test_login_recovery_rejects_unknown_code(client):
    from app import app as flask_app
    with flask_app.app_context():
        username, password, _ = _make_enrolled_superadmin(slug="t6")
    pending = client.post(
        "/api/v2/auth/login",
        json={"username": username, "password": password, "store_id": None},
    ).get_json()["pending_token"]
    resp = client.post(
        "/api/v2/auth/login/recovery",
        json={"pending_token": pending, "code": "WRONG-CODE"},
    )
    assert resp.status_code == 401


def test_login_recovery_code_is_single_use(client):
    """Reusing the same recovery code on a second exchange fails."""
    from app import app as flask_app
    with flask_app.app_context():
        username, password, _ = _make_enrolled_superadmin(slug="t7")
        _add_recovery_code(username, "ONEUSE12")
    pending = client.post(
        "/api/v2/auth/login",
        json={"username": username, "password": password, "store_id": None},
    ).get_json()["pending_token"]
    first = client.post(
        "/api/v2/auth/login/recovery",
        json={"pending_token": pending, "code": "ONEUSE12"},
    )
    assert first.status_code == 200
    # Second attempt with a fresh pending token but the same code
    pending2 = client.post(
        "/api/v2/auth/login",
        json={"username": username, "password": password, "store_id": None},
    ).get_json()["pending_token"]
    second = client.post(
        "/api/v2/auth/login/recovery",
        json={"pending_token": pending2, "code": "ONEUSE12"},
    )
    assert second.status_code == 401


# ── Cross-store login also gates 2FA ────────────────────────


def test_login_cross_store_gates_2fa(client):
    from app import app as flask_app
    with flask_app.app_context():
        username, password, _ = _make_enrolled_superadmin(slug="t8")
    resp = client.post(
        "/api/v2/auth/login-cross-store",
        json={"username": username, "password": password},
    )
    body = resp.get_json()
    assert body["requires_totp"] is True
    assert body["pending_token"]


# ── Pending token can't authorize requests ──────────────────


def test_pending_token_rejected_by_authed_endpoint(client):
    """A pending token has `purpose=totp-pending`, which
    decode_access_token rejects. So even if a client tries to use
    it as a Bearer token, /auth/me returns 401."""
    from app import app as flask_app
    with flask_app.app_context():
        username, password, _ = _make_enrolled_superadmin(slug="t9")
    pending = client.post(
        "/api/v2/auth/login",
        json={"username": username, "password": password, "store_id": None},
    ).get_json()["pending_token"]
    resp = client.get(
        "/api/v2/auth/me",
        headers={"Authorization": f"Bearer {pending}"},
    )
    assert resp.status_code == 401
