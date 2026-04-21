"""Tests for the mandatory TOTP 2FA flow on superadmin login.

Covers:
  - First-ever superadmin login is redirected to enrollment.
  - Wrong confirmation code on enrollment stays on the page.
  - Successful enrollment mints 10 recovery codes and requires the
    "I've saved these" checkbox before finalizing.
  - Post-enrollment login requires the 6-digit code (or a recovery code).
  - Recovery codes are single-use.
  - /forgot-password silently ignores the superadmin account.
  - /reset-password refuses to honor a token for a superadmin even if
    one somehow exists.
"""
import pyotp
from datetime import datetime, timedelta


# ── helpers ──────────────────────────────────────────────────

def _current_totp(secret):
    return pyotp.TOTP(secret).now()


def _superadmin_row():
    from app import User
    return User.query.filter_by(username="superadmin", store_id=None).first()


def _post_login(client, username="superadmin", password="super2025!"):
    return client.post("/login", data={"username": username, "password": password},
                       follow_redirects=False)


# ── enrollment flow ──────────────────────────────────────────

def test_first_superadmin_login_redirects_to_enrollment(client):
    resp = _post_login(client)
    assert resp.status_code == 302
    assert "/login/2fa/enroll" in resp.headers["Location"]
    with client.session_transaction() as sess:
        assert sess.get("pending_auth_user_id")
        assert "user_id" not in sess


def test_enrollment_page_shows_qr_and_secret(client):
    _post_login(client)
    resp = client.get("/login/2fa/enroll")
    assert resp.status_code == 200
    assert b"<svg" in resp.data
    assert b"Two-factor" in resp.data or b"two-factor" in resp.data.lower()
    # Pending secret must be persisted so refreshing the page doesn't
    # rotate it out from under the user's already-scanned QR.
    with client.application.app_context():
        sa = _superadmin_row()
        assert sa.totp_secret is not None
        assert sa.totp_enrolled_at is None


def test_enrollment_wrong_code_stays_on_page(client):
    _post_login(client)
    client.get("/login/2fa/enroll")
    resp = client.post("/login/2fa/enroll", data={"code": "000000"})
    assert resp.status_code == 200
    assert b"didn" in resp.data.lower()  # "didn't match"
    with client.application.app_context():
        assert _superadmin_row().totp_enrolled_at is None


def test_enrollment_completes_and_shows_recovery_codes(client):
    _post_login(client)
    client.get("/login/2fa/enroll")
    with client.application.app_context():
        secret = _superadmin_row().totp_secret
    resp = client.post("/login/2fa/enroll", data={"code": _current_totp(secret)},
                       follow_redirects=False)
    assert resp.status_code == 302
    assert "/login/2fa/recovery-codes" in resp.headers["Location"]

    with client.application.app_context():
        from app import RecoveryCode
        sa = _superadmin_row()
        assert sa.totp_enrolled_at is not None
        assert RecoveryCode.query.filter_by(user_id=sa.id).count() == 10

    page = client.get("/login/2fa/recovery-codes")
    assert page.status_code == 200
    # Ten 8-char codes (with a hyphen at position 5) show up on the page.
    assert page.data.count(b"-") >= 10


def test_recovery_codes_page_requires_user_still_authing(client):
    """Direct visit without going through /login first → redirect to /login."""
    resp = client.get("/login/2fa/recovery-codes", follow_redirects=False)
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]


def test_finalize_after_saving_codes_sets_full_session(client):
    _post_login(client)
    client.get("/login/2fa/enroll")
    with client.application.app_context():
        secret = _superadmin_row().totp_secret
    client.post("/login/2fa/enroll", data={"code": _current_totp(secret)})
    resp = client.post("/login/2fa/recovery-codes", data={"saved": "1"},
                       follow_redirects=False)
    assert resp.status_code == 302
    with client.session_transaction() as sess:
        assert sess.get("user_id")
        assert "pending_auth_user_id" not in sess
        assert "totp_enrollment_codes" not in sess


# ── post-enrollment login flow ───────────────────────────────

def _enroll_superadmin(client):
    """Complete enrollment end-to-end and return (secret, recovery_codes)."""
    _post_login(client)
    client.get("/login/2fa/enroll")
    with client.application.app_context():
        secret = _superadmin_row().totp_secret
    client.post("/login/2fa/enroll", data={"code": _current_totp(secret)})
    # Scrape the plaintext codes off the recovery-codes page.
    page = client.get("/login/2fa/recovery-codes")
    import re
    codes = re.findall(rb"[A-F0-9]{4}-[A-F0-9]{4}", page.data)
    codes = [c.decode() for c in codes]
    client.post("/login/2fa/recovery-codes", data={"saved": "1"})
    client.get("/logout")
    return secret, codes


def test_second_login_prompts_for_totp(client):
    _enroll_superadmin(client)
    resp = _post_login(client)
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/login/2fa")


def test_valid_totp_logs_in(client):
    secret, _ = _enroll_superadmin(client)
    _post_login(client)
    resp = client.post("/login/2fa", data={"code": _current_totp(secret)},
                       follow_redirects=False)
    assert resp.status_code == 302
    assert "dashboard" in resp.headers["Location"]
    with client.session_transaction() as sess:
        assert sess.get("user_id")
        assert sess.get("role") == "superadmin"


def test_invalid_totp_stays_on_prompt(client):
    _enroll_superadmin(client)
    _post_login(client)
    resp = client.post("/login/2fa", data={"code": "000000"})
    assert resp.status_code == 200
    assert b"didn" in resp.data.lower()
    with client.session_transaction() as sess:
        assert "user_id" not in sess


def test_recovery_code_logs_in_and_is_single_use(client):
    _, codes = _enroll_superadmin(client)
    first = codes[0]

    # First use: succeeds.
    _post_login(client)
    resp = client.post("/login/2fa/recover", data={"code": first},
                       follow_redirects=False)
    assert resp.status_code == 302
    assert "dashboard" in resp.headers["Location"]
    client.get("/logout")

    # Second use of the same code: fails.
    _post_login(client)
    resp = client.post("/login/2fa/recover", data={"code": first})
    assert resp.status_code == 200
    assert b"not recognized" in resp.data.lower() or b"already used" in resp.data.lower()


def test_recovery_code_accepts_lowercase_and_stripped(client):
    _, codes = _enroll_superadmin(client)
    # Paste the code in lowercase, with extra whitespace — should still work.
    messy = f"  {codes[1].lower()}  "
    _post_login(client)
    resp = client.post("/login/2fa/recover", data={"code": messy},
                       follow_redirects=False)
    assert resp.status_code == 302
    assert "dashboard" in resp.headers["Location"]


# ── password-reset gate ──────────────────────────────────────

def test_forgot_password_ignores_superadmin(client):
    """Superadmin is deliberately excluded from the email-reset flow."""
    from app import PasswordResetToken
    # Same friendly "check your email" page, no token minted.
    resp = client.post("/forgot-password", data={"username": "superadmin"})
    assert resp.status_code == 200
    with client.application.app_context():
        assert PasswordResetToken.query.count() == 0


def test_reset_password_refuses_superadmin_token(client):
    """Belt-and-suspenders: even a direct DB-inserted token is rejected
    for a superadmin target."""
    import hashlib
    from app import db, PasswordResetToken
    with client.application.app_context():
        sa = _superadmin_row()
        raw = "direct-insert-token-should-not-work"
        tok = PasswordResetToken(
            user_id=sa.id,
            token_hash=hashlib.sha256(raw.encode()).hexdigest(),
            expires_at=datetime.utcnow() + timedelta(hours=1),
        )
        db.session.add(tok)
        db.session.commit()
    resp = client.get(f"/reset-password/{raw}")
    assert resp.status_code == 200
    # Template renders the invalid-token branch.
    assert b"invalid" in resp.data.lower() or b"expired" in resp.data.lower()


# ── hardening: employee/owner/admin still skip 2FA ───────────

def test_admin_login_is_unaffected_by_2fa(client):
    """Only superadmin gets the 2FA gate. Regular admin → straight to dashboard."""
    resp = client.post("/login",
                       data={"username": "admin@test.com", "password": "testpass123!"},
                       follow_redirects=False)
    assert resp.status_code == 302
    assert "dashboard" in resp.headers["Location"]
    with client.session_transaction() as sess:
        assert sess.get("user_id")
        assert "pending_auth_user_id" not in sess
