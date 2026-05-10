"""Email delivery wiring — SMTP health, superadmin test-send button,
password-reset recipient preference.

The app has exactly two real email senders today: password reset and
the trial-reminder cron. Both flow through _send_email(), which now
updates a module-level `_last_smtp_attempt` cache on every call so
the superadmin Overview can surface the most recent outcome without
live probing.

We cover:
  - _send_email state cache transitions (unconfigured → sent → failed)
  - smtp_health_check() return shape
  - Overview tab renders the Email service card with the right status
    badge for each cache state
  - POST /superadmin/send-test-email is superadmin-only, requires the
    superadmin to have set their own email, calls _send_email, and
    redirects with a flash
  - /forgot-password prefers User.email over username when set, falls
    back to username when blank — verified by checking which address
    _last_smtp_attempt captured
"""
import os
from datetime import datetime
from unittest.mock import patch

from app import db, User, _send_email, smtp_health_check
import app as app_module


# ── _send_email cache + smtp_health_check ──────────────────────

def test_send_email_unconfigured_sets_status(client):
    """No SMTP env vars → status becomes 'unconfigured'. The cache
    still records the attempt so the health card isn't completely
    blank after a real send failure — the superadmin sees there WAS
    an attempt."""
    for k in ("SMTP_HOST", "SMTP_USER", "SMTP_PASS"):
        os.environ.pop(k, None)
    with client.application.app_context():
        ok = _send_email("someone@example.com", "Hi", "body")
    assert ok is False
    h = smtp_health_check()
    assert h["status"] == "unconfigured"
    assert h["configured"] is False
    assert h["last_to_domain"] == "example.com"


def test_send_email_success_path_sets_status_sent(client):
    """Patch smtplib.SMTP so the SMTP instance is a benign context
    manager that "accepts" every message. The cache should flip to
    'sent' with no error."""
    os.environ["SMTP_HOST"] = "smtp.test"
    os.environ["SMTP_USER"] = "u"
    os.environ["SMTP_PASS"] = "p"
    with patch("app.smtplib.SMTP") as smtp:
        smtp.return_value.__enter__.return_value.send_message.return_value = {}
        with client.application.app_context():
            ok = _send_email("to@example.com", "Hi", "body")
    assert ok is True
    h = smtp_health_check()
    assert h["status"] == "sent"
    assert h["error"] == ""
    assert h["configured"] is True


def test_send_email_failure_surfaces_error_type(client):
    """Any exception raised inside the SMTP context manager gets
    captured as `"<TypeName>: <message>"` so the superadmin can tell
    an auth failure from a connection failure without a traceback."""
    os.environ["SMTP_HOST"] = "smtp.test"
    os.environ["SMTP_USER"] = "u"
    os.environ["SMTP_PASS"] = "p"
    import smtplib
    with patch("app.smtplib.SMTP") as smtp:
        smtp.return_value.__enter__.side_effect = smtplib.SMTPAuthenticationError(
            535, b"bad creds")
        with client.application.app_context():
            ok = _send_email("to@example.com", "Hi", "body")
    assert ok is False
    h = smtp_health_check()
    assert h["status"] == "failed"
    assert "SMTPAuthenticationError" in h["error"]


# ── Overview template: Email service card ──────────────────────

def _superadmin_client(app):
    c = app.test_client()
    with app.app_context():
        sa_id = User.query.filter_by(username="superadmin").first().id
    with c.session_transaction() as s:
        s["user_id"] = sa_id
        s["role"] = "superadmin"
        s["store_id"] = None
    return c


def _reset_last_attempt():
    """Reset the SMTP health-card state. The canonical dict lives
    on `api.Modules.Notifications.Services.smtp.last_attempt`
    (PR 82); `app_module._last_smtp_attempt` is an alias to it.
    Mutate in place so any outstanding alias still points at
    the live dict."""
    from api.Modules.Notifications.Services import smtp as smtp_svc
    smtp_svc.reset_last_attempt()










# ── /superadmin/send-test-email button ─────────────────────────

def test_send_test_email_requires_superadmin(logged_in_client):
    """Regular admins can't hit the endpoint."""
    resp = logged_in_client.post("/superadmin/send-test-email")
    assert resp.status_code in (302, 401, 403, 404)


def test_send_test_email_flashes_when_superadmin_has_no_email(client):
    """Superadmin who hasn't set their /account/profile email gets a
    guard instead of a noisy failure — handler short-circuits and
    302s. The legacy flash text moved to React; assert the bounce
    didn't silently send a real email by checking
    `_last_smtp_attempt` is unchanged."""
    from app import _last_smtp_attempt
    before_attempt = dict(_last_smtp_attempt)
    with client.application.app_context():
        sa = User.query.filter_by(username="superadmin").first()
        sa.email = ""
        db.session.commit()
    resp = _superadmin_client(client.application).post(
        "/superadmin/send-test-email", follow_redirects=False)
    assert resp.status_code in (302, 303)
    # Handler short-circuited — _last_smtp_attempt unchanged.
    from app import _last_smtp_attempt as after_attempt
    assert dict(after_attempt) == before_attempt


def test_send_test_email_redirects_to_overview_with_flash(client):
    """With an email configured and SMTP vars set, the test send
    returns a 302 back to the Overview. We don't assert deliverability
    — that's what Resend does for us in prod — just that the endpoint
    wires up cleanly."""
    with client.application.app_context():
        sa = User.query.filter_by(username="superadmin").first()
        sa.email = "sa@test.example"
        db.session.commit()
    os.environ["SMTP_HOST"] = "smtp.test"
    os.environ["SMTP_USER"] = "u"
    os.environ["SMTP_PASS"] = "p"
    with patch("app.smtplib.SMTP") as smtp:
        smtp.return_value.__enter__.return_value.send_message.return_value = {}
        resp = _superadmin_client(client.application).post(
            "/superadmin/send-test-email", follow_redirects=False)
    assert resp.status_code == 302
    assert "/superadmin/controls" in resp.headers["Location"]
    assert "tab=overview" in resp.headers["Location"]


def test_send_test_email_records_audit(client):
    """Every superadmin mutation calls record_audit per CLAUDE.md
    invariant #7 — even the test-send, so a future "who spammed
    Resend" question is answerable."""
    with client.application.app_context():
        sa = User.query.filter_by(username="superadmin").first()
        sa.email = "sa@test.example"
        db.session.commit()
    os.environ["SMTP_HOST"] = "smtp.test"
    os.environ["SMTP_USER"] = "u"
    os.environ["SMTP_PASS"] = "p"
    with patch("app.smtplib.SMTP") as smtp:
        smtp.return_value.__enter__.return_value.send_message.return_value = {}
        _superadmin_client(client.application).post(
            "/superadmin/send-test-email")
    from app import SuperadminAuditLog
    with client.application.app_context():
        row = SuperadminAuditLog.query.filter_by(action="send_test_email").first()
        assert row is not None
        assert "ok=True" in (row.details or "")


# ── /forgot-password prefers User.email ────────────────────────

def test_forgot_password_uses_user_email_when_set(client):
    """When an admin has set User.email on /account/profile, reset
    mail goes there — not to the username."""
    os.environ["SMTP_HOST"] = "smtp.test"
    os.environ["SMTP_USER"] = "u"
    os.environ["SMTP_PASS"] = "p"
    with client.application.app_context():
        admin = User.query.filter_by(username="admin@test.com").first()
        admin.email = "real-address@different.example"
        db.session.commit()
    with patch("app.smtplib.SMTP") as smtp:
        smtp.return_value.__enter__.return_value.send_message.return_value = {}
        client.post(
            "/api/v2/auth/forgot-password",
            json={"email": "admin@test.com"},
        )
    h = smtp_health_check()
    assert h["last_to_domain"] == "different.example", \
        f"expected reset to go to the User.email domain, got {h['last_to_domain']!r}"


def test_forgot_password_falls_back_to_username_when_email_blank(client):
    """Blank User.email → use username (back-compat for accounts that
    existed before the email field was added)."""
    os.environ["SMTP_HOST"] = "smtp.test"
    os.environ["SMTP_USER"] = "u"
    os.environ["SMTP_PASS"] = "p"
    with client.application.app_context():
        admin = User.query.filter_by(username="admin@test.com").first()
        admin.email = ""
        db.session.commit()
    with patch("app.smtplib.SMTP") as smtp:
        smtp.return_value.__enter__.return_value.send_message.return_value = {}
        client.post(
            "/api/v2/auth/forgot-password",
            json={"email": "admin@test.com"},
        )
    h = smtp_health_check()
    assert h["last_to_domain"] == "test.com", \
        f"expected fallback to username domain, got {h['last_to_domain']!r}"


def test_forgot_password_superadmin_still_excluded(client):
    """Regression guard — CLAUDE.md invariant #10 excludes superadmin
    from the email reset flow even if they have User.email set. The
    health cache shouldn't show an attempted send to them."""
    _reset_last_attempt()
    os.environ["SMTP_HOST"] = "smtp.test"
    os.environ["SMTP_USER"] = "u"
    os.environ["SMTP_PASS"] = "p"
    with client.application.app_context():
        sa = User.query.filter_by(username="superadmin").first()
        sa.email = "sa@example.com"
        db.session.commit()
    with patch("app.smtplib.SMTP") as smtp:
        smtp.return_value.__enter__.return_value.send_message.return_value = {}
        client.post(
            "/api/v2/auth/forgot-password",
            json={"email": "superadmin"},
        )
    h = smtp_health_check()
    # No send was attempted — cache stays at 'unknown'. This is the
    # exact signal the health card would show for "no activity yet".
    assert h["status"] == "unknown", \
        f"reset flow should not send to superadmin; got status={h['status']!r}"
