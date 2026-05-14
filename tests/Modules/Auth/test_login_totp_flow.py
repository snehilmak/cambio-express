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
from tests._app import db


def _make_enrolled_superadmin(*, slug="ts2fa"):
    """Create a brand-new superadmin User with TOTP enrolled.
    Returns (username, password, totp_secret). Each test gets its
    own row so we don't mutate the shared seeded `superadmin`."""
    from api.Modules.Tenancy.Models import User
    from tests._app import db
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
    from api.Modules.Auth.Models import RecoveryCode
    from api.Modules.Tenancy.Models import User
    from tests._app import db
    from api.Modules.Auth.Services.totp import hash_recovery_code
    sa = db.session.query(User).filter_by(username=username).first()
    db.session.add(RecoveryCode(
        user_id=sa.id, code_hash=hash_recovery_code(raw_code),
    ))
    db.session.commit()


# ── Pending-token issuance ──────────────────────────────────


def test_login_returns_pending_when_superadmin_enrolled(client):
    from tests._app import app as flask_app
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
    from tests._app import app as flask_app
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


def test_login_unenrolled_superadmin_returns_enroll_required(client):
    """An unenrolled superadmin now gets a 2FA-pending response with
    `enroll_required=True`, so the SPA can route them to the
    /app/login/2fa/enroll page and drive enrollment via the
    /auth/login/totp/enroll/* set. We create a fresh User here
    rather than mutate the seeded `superadmin` (which is pre-
    enrolled in conftest)."""
    from api.Modules.Tenancy.Models import User
    from tests._app import app as flask_app, db
    with flask_app.app_context():
        u = User(
            store_id=None, username="ne@super",
            full_name="Not Enrolled", role="superadmin",
        )
        u.set_password("ne2025!")
        db.session.add(u); db.session.commit()
    resp = client.post(
        "/api/v2/auth/login",
        json={
            "username": "ne@super", "password": "ne2025!",
            "store_id": None,
        },
    )
    body = resp.get_json()
    assert body["requires_totp"] is True
    assert body["enroll_required"] is True
    assert body["pending_token"]
    assert body["access_token"] == ""
    # No recovery codes exist for an unenrolled user.
    assert body["has_recovery_codes"] is False


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
    from tests._app import app as flask_app
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
    from tests._app import app as flask_app
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
    from api.Modules.Auth.Models import RecoveryCode
    from tests._app import app as flask_app
    with flask_app.app_context():
        username, password, _ = _make_enrolled_superadmin(slug="t5")
        _add_recovery_code(username, "WXYZ7890")
        before = db.session.query(RecoveryCode).filter_by(used_at=None).count()
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
        after = db.session.query(RecoveryCode).filter_by(used_at=None).count()
    assert after == before - 1


def test_login_recovery_rejects_unknown_code(client):
    from tests._app import app as flask_app
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
    from tests._app import app as flask_app
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
    from tests._app import app as flask_app
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
    from tests._app import app as flask_app
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


# ── /auth/login/totp/enroll/* — SPA-driven enrollment ───────


def _make_unenrolled_superadmin(*, slug="tsne"):
    """Brand-new superadmin with no TOTP secret yet. Returns
    (username, password). The /login response will carry
    `requires_totp=True, enroll_required=True`."""
    from api.Modules.Tenancy.Models import User
    from tests._app import db
    username = f"{slug}@superadmin"
    user = User(
        store_id=None, username=username,
        full_name="Fresh Super", role="superadmin",
    )
    user.set_password("super2025!")
    db.session.add(user); db.session.commit()
    return username, "super2025!"


def _start_enroll_for(client, slug):
    """Helper: log in, get pending token, call enroll/start.
    Returns (pending_token, start_response_dict)."""
    from tests._app import app as flask_app
    with flask_app.app_context():
        username, password = _make_unenrolled_superadmin(slug=slug)
    pending = client.post(
        "/api/v2/auth/login",
        json={"username": username, "password": password, "store_id": None},
    ).get_json()["pending_token"]
    start = client.post(
        "/api/v2/auth/login/totp/enroll/start",
        json={"pending_token": pending},
    )
    return pending, start.get_json()


def test_enroll_start_returns_qr_secret_and_chunks(client):
    pending, body = _start_enroll_for(client, "te1")
    assert body["secret"]
    # Base32 secret is 32 chars from pyotp.random_base32()
    assert len(body["secret"]) == 32
    # Chunks join the secret in 4-char pieces with spaces
    assert body["secret_chunks"].replace(" ", "") == body["secret"]
    # QR is a stand-alone SVG document (qrcode.image.svg returns an
    # XML wrapper plus the embedded svg root)
    assert "<svg" in body["qr_svg"]
    assert body["issuer"] == "DineroBook"
    assert body["username"].endswith("@superadmin")


def test_enroll_start_is_idempotent_returns_same_secret(client):
    """Calling enroll/start twice with the same pending token must
    return the same secret so a half-scanned QR stays valid."""
    pending, body1 = _start_enroll_for(client, "te2")
    body2 = client.post(
        "/api/v2/auth/login/totp/enroll/start",
        json={"pending_token": pending},
    ).get_json()
    assert body1["secret"] == body2["secret"]


def test_enroll_start_rejects_bad_pending_token(client):
    resp = client.post(
        "/api/v2/auth/login/totp/enroll/start",
        json={"pending_token": "not-a-real-token"},
    )
    assert resp.status_code == 401


def test_enroll_finish_verifies_code_and_returns_recovery_codes(client):
    pending, start = _start_enroll_for(client, "te3")
    code = pyotp.TOTP(start["secret"]).now()
    resp = client.post(
        "/api/v2/auth/login/totp/enroll/finish",
        json={"pending_token": pending, "code": code},
    )
    assert resp.status_code == 200
    codes = resp.get_json()["recovery_codes"]
    assert len(codes) == 10
    # Codes are formatted as ABCD-EFGH (8 hex + hyphen)
    assert all(len(c) == 9 and c[4] == "-" for c in codes)


def test_enroll_finish_rejects_bad_code(client):
    pending, _ = _start_enroll_for(client, "te4")
    resp = client.post(
        "/api/v2/auth/login/totp/enroll/finish",
        json={"pending_token": pending, "code": "000000"},
    )
    assert resp.status_code == 401


def test_enroll_finish_marks_user_enrolled(client):
    from api.Modules.Tenancy.Models import User
    from tests._app import app as flask_app
    pending, start = _start_enroll_for(client, "te5")
    code = pyotp.TOTP(start["secret"]).now()
    client.post(
        "/api/v2/auth/login/totp/enroll/finish",
        json={"pending_token": pending, "code": code},
    )
    with flask_app.app_context():
        u = db.session.query(User).filter_by(username="te5@superadmin").first()
        assert u.totp_secret == start["secret"]
        assert u.totp_enrolled_at is not None


def test_enroll_confirm_issues_full_access_token(client):
    pending, start = _start_enroll_for(client, "te6")
    code = pyotp.TOTP(start["secret"]).now()
    client.post(
        "/api/v2/auth/login/totp/enroll/finish",
        json={"pending_token": pending, "code": code},
    )
    resp = client.post(
        "/api/v2/auth/login/totp/enroll/confirm",
        json={"pending_token": pending},
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["access_token"]
    assert body["requires_totp"] is False
    assert body["role"] == "superadmin"
    assert body["store_id"] is None


def test_enroll_confirm_rejected_before_finish(client):
    """Calling confirm before finish (no totp_enrolled_at yet) must
    return 401 — there's no actual enrollment to confirm."""
    pending, _start = _start_enroll_for(client, "te7")
    resp = client.post(
        "/api/v2/auth/login/totp/enroll/confirm",
        json={"pending_token": pending},
    )
    assert resp.status_code == 401
