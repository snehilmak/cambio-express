"""Tests for the superadmin TOTP 2FA password-reset gating + the
admin-role carve-out from the 2FA hop.

The SPA-driven 2FA flow itself (login pending shape, TOTP exchange,
recovery codes, enrollment) is exercised in
tests/Modules/Auth/test_login_totp_flow.py — that test file talks
directly to the FastAPI endpoints. The legacy Jinja /login/2fa*
routes are now 301 redirects to /app/login (SPA owns rendering),
so the GET/POST exercises that used to live here moved to the
FastAPI suite.

What we still verify here:
  - /forgot-password silently ignores the superadmin account.
  - /reset-password refuses to honour a token for a superadmin
    even if one is direct-inserted in the DB.
  - Regular admins (not superadmin) skip the 2FA hop entirely on
    the legacy /login route.
"""
from datetime import datetime, timedelta


def _superadmin_row():
    from app import User
    return User.query.filter_by(username="superadmin", store_id=None).first()


# ── password-reset gate ──────────────────────────────────────


def test_forgot_password_ignores_superadmin(client):
    """Superadmin is deliberately excluded from the email-reset
    flow. The SPA submits to /api/v2/auth/forgot-password — the
    endpoint always responds 200 (no enumeration leak) but no
    token is minted for the superadmin role."""
    from app import PasswordResetToken
    resp = client.post(
        "/api/v2/auth/forgot-password",
        json={"email": "superadmin"},
    )
    assert resp.status_code == 200
    with client.application.app_context():
        assert PasswordResetToken.query.count() == 0


def test_reset_password_refuses_superadmin_token(client):
    """Belt-and-suspenders: even a direct DB-inserted token is
    rejected for a superadmin target. The SPA reset endpoint
    returns 400 for any invalid/superadmin-targeted token."""
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
    resp = client.post(
        "/api/v2/auth/reset-password",
        json={
            "token": raw,
            "new_password": "newpass123!",
            "confirm_password": "newpass123!",
        },
    )
    assert resp.status_code == 400
    body = resp.get_json()
    assert "invalid" in str(body.get("detail", "")).lower() \
        or "expired" in str(body.get("detail", "")).lower()


# ── hardening: employee/owner/admin still skip 2FA ───────────


def test_admin_login_is_unaffected_by_2fa(client):
    """Only superadmin gets the 2FA gate. Regular admin → straight
    to dashboard via the legacy /login form."""
    resp = client.post(
        "/login",
        data={"username": "admin@test.com", "password": "testpass123!"},
        follow_redirects=False,
    )
    assert resp.status_code == 302
    assert "dashboard" in resp.headers["Location"]
    with client.session_transaction() as sess:
        assert sess.get("user_id")
        assert "pending_auth_user_id" not in sess
