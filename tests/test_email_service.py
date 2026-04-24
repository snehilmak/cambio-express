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
    app_module._last_smtp_attempt = {
        "status": "unknown", "error": "", "when": None,
        "last_to_domain": "", "last_subject": "",
    }


def test_overview_renders_email_service_card(client):
    _reset_last_attempt()
    body = _superadmin_client(client.application).get(
        "/superadmin/controls?tab=overview").data.decode()
    assert "Email service" in body
    assert "SMTP_HOST" in body
    assert "Send test email" in body


def test_overview_shows_not_configured_when_env_missing(client):
    for k in ("SMTP_HOST", "SMTP_USER", "SMTP_PASS"):
        os.environ.pop(k, None)
    _reset_last_attempt()
    body = _superadmin_client(client.application).get(
        "/superadmin/controls?tab=overview").data.decode()
    assert "Not configured" in body
    # Button is disabled when env vars are missing — clicking would be
    # a guaranteed failure, so we prevent it at the UI level.
    assert "disabled" in body


def test_overview_shows_connected_when_last_send_succeeded(client):
    os.environ["SMTP_HOST"] = "smtp.test"
    os.environ["SMTP_USER"] = "u"
    os.environ["SMTP_PASS"] = "p"
    app_module._last_smtp_attempt = {
        "status": "sent", "error": "",
        "when": datetime(2025, 1, 15, 10, 30, 0),
        "last_to_domain": "customer.example", "last_subject": "X",
    }
    body = _superadmin_client(client.application).get(
        "/superadmin/controls?tab=overview").data.decode()
    assert "Connected" in body
    # Only the recipient's domain is shown, never the full address
    # (the health card is viewed by superadmin but user emails are
    # still personal data we don't need to surface here).
    assert "*@customer.example" in body


def test_overview_shows_failing_with_error_on_last_send_failure(client):
    os.environ["SMTP_HOST"] = "smtp.test"
    os.environ["SMTP_USER"] = "u"
    os.environ["SMTP_PASS"] = "p"
    app_module._last_smtp_attempt = {
        "status": "failed",
        "error": "SMTPAuthenticationError: 535 bad creds",
        "when": datetime(2025, 1, 15, 10, 30, 0),
        "last_to_domain": "customer.example", "last_subject": "X",
    }
    body = _superadmin_client(client.application).get(
        "/superadmin/controls?tab=overview").data.decode()
    assert "Failing" in body
    assert "bad creds" in body


# ── /superadmin/send-test-email button ─────────────────────────

def test_send_test_email_requires_superadmin(logged_in_client):
    """Regular admins can't hit the endpoint."""
    resp = logged_in_client.post("/superadmin/send-test-email")
    assert resp.status_code in (302, 401, 403, 404)


def test_send_test_email_flashes_when_superadmin_has_no_email(client):
    """Superadmin who hasn't set their /account/profile email gets a
    guard instead of a noisy failure — nowhere to send the test to."""
    with client.application.app_context():
        sa = User.query.filter_by(username="superadmin").first()
        sa.email = ""
        db.session.commit()
    resp = _superadmin_client(client.application).post(
        "/superadmin/send-test-email", follow_redirects=True)
    body = resp.data.decode()
    assert "Set your email" in body or "set your email" in body


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
        client.post("/forgot-password", data={"username": "admin@test.com"})
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
        client.post("/forgot-password", data={"username": "admin@test.com"})
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
        client.post("/forgot-password", data={"username": "superadmin"})
    h = smtp_health_check()
    # No send was attempted — cache stays at 'unknown'. This is the
    # exact signal the health card would show for "no activity yet".
    assert h["status"] == "unknown", \
        f"reset flow should not send to superadmin; got status={h['status']!r}"
