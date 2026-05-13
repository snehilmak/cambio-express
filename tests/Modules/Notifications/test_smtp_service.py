"""Unit tests for Notifications.Services.smtp (PR 82)."""
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

from api.Modules.Tenancy.Models import User
from api.Modules.Webhooks.Models import EmailEvent


def _add_user(db, *, email, store_id=1, bounced=False):
    u = User(
        username=email,
        password_hash="x", role="admin",
        full_name="x", email=email, store_id=store_id,
    )
    if bounced:
        u.email_bounced_at = datetime.utcnow()
    db.add(u); db.flush()
    return u


def _set_smtp_env(monkeypatch, *,
                   host="smtp.example.com",
                   user="apikey",
                   pw="abc123",
                   port="587",
                   sender=None):
    """Set the standard SMTP env vars."""
    if host:
        monkeypatch.setenv("SMTP_HOST", host)
    else:
        monkeypatch.delenv("SMTP_HOST", raising=False)
    if user:
        monkeypatch.setenv("SMTP_USER", user)
    else:
        monkeypatch.delenv("SMTP_USER", raising=False)
    if pw:
        monkeypatch.setenv("SMTP_PASS", pw)
    else:
        monkeypatch.delenv("SMTP_PASS", raising=False)
    if port:
        monkeypatch.setenv("SMTP_PORT", port)
    if sender is not None:
        monkeypatch.setenv("SMTP_FROM", sender)


def _reset_attempt():
    from api.Modules.Notifications.Services import smtp as smtp_svc
    smtp_svc.reset_last_attempt()


# ── send_email — env validation ───────────────────────────


def test_send_returns_false_when_unconfigured(monkeypatch):
    """Missing env vars → no send + status 'unconfigured'."""
    from app import app as flask_app, db
    from api.Modules.Notifications.Services import (
        send_email, smtp as smtp_svc,
    )
    _reset_attempt()
    _set_smtp_env(monkeypatch, host=None)
    with flask_app.app_context():
        result = send_email(db.session, "test@example.com",
                              "Subject", "Body")
        assert result is False
        assert smtp_svc.last_attempt["status"] == "unconfigured"


def test_send_returns_false_when_only_host_set(monkeypatch):
    """Partial config (no user/pw) → unconfigured, not crash."""
    from app import app as flask_app, db
    from api.Modules.Notifications.Services import send_email
    from api.Modules.Notifications.Services import smtp as smtp_svc
    _reset_attempt()
    _set_smtp_env(monkeypatch, user=None, pw=None)
    with flask_app.app_context():
        assert send_email(db.session, "x@y.com", "S", "B") is False
        assert smtp_svc.last_attempt["status"] == "unconfigured"


# ── send_email — bounce suppression ───────────────────────


def test_send_suppressed_for_bounced_user(monkeypatch):
    """User with email_bounced_at set → skip the send entirely."""
    from app import app as flask_app, db
    from api.Modules.Notifications.Services import send_email
    from api.Modules.Notifications.Services import smtp as smtp_svc
    _reset_attempt()
    _set_smtp_env(monkeypatch)
    with flask_app.app_context():
        User.query.filter_by(email="bounced@example.com").delete()
        db.session.commit()
        _add_user(db.session, email="bounced@example.com",
                   bounced=True)
        db.session.flush()
        with patch("smtplib.SMTP") as smtp_mock:
            result = send_email(
                db.session, "bounced@example.com",
                "Hi", "Body",
            )
        assert result is False
        assert smtp_svc.last_attempt["status"] == "suppressed"
        # SMTP wasn't even instantiated.
        assert smtp_mock.call_count == 0


def test_send_suppression_lookup_is_case_insensitive(monkeypatch):
    from app import app as flask_app, db
    from api.Modules.Notifications.Services import send_email
    from api.Modules.Notifications.Services import smtp as smtp_svc
    _reset_attempt()
    _set_smtp_env(monkeypatch)
    with flask_app.app_context():
        User.query.filter_by(
            email="Bounced.Mixed@Example.com",
        ).delete()
        db.session.commit()
        _add_user(db.session,
                   email="Bounced.Mixed@Example.com",
                   bounced=True)
        db.session.flush()
        with patch("smtplib.SMTP"):
            # Different casing in the to_addr — still matches.
            result = send_email(
                db.session, "BOUNCED.MIXED@example.com",
                "Hi", "Body",
            )
        assert result is False
        assert smtp_svc.last_attempt["status"] == "suppressed"


def test_send_attempts_when_no_user_match(monkeypatch):
    """Address with no matching User row → no suppression check
    blocks; the send proceeds (and may succeed or fail on its
    own merits)."""
    from app import app as flask_app, db
    from api.Modules.Notifications.Services import send_email
    from api.Modules.Notifications.Services import smtp as smtp_svc
    _reset_attempt()
    _set_smtp_env(monkeypatch)
    with flask_app.app_context():
        User.query.filter_by(
            email="superadmin-test@example.com",
        ).delete()
        db.session.commit()
        with patch("smtplib.SMTP") as smtp_mock:
            smtp_mock.return_value.__enter__.return_value = (
                MagicMock()
            )
            result = send_email(
                db.session, "superadmin-test@example.com",
                "Test", "Hello",
            )
        assert result is True
        assert smtp_svc.last_attempt["status"] == "sent"


# ── send_email — happy path ───────────────────────────────


def test_send_calls_smtp_with_starttls_and_login(monkeypatch):
    from app import app as flask_app, db
    from api.Modules.Notifications.Services import send_email
    from api.Modules.Notifications.Services import smtp as smtp_svc
    _reset_attempt()
    _set_smtp_env(monkeypatch, host="smtp.example.com",
                   user="apikey", pw="secret", port="587")
    with flask_app.app_context():
        User.query.filter_by(email="t@example.com").delete()
        db.session.commit()
        with patch("smtplib.SMTP") as smtp_mock:
            inst = MagicMock()
            smtp_mock.return_value.__enter__.return_value = inst
            assert send_email(
                db.session, "t@example.com",
                "S", "Plain", html="<b>HTML</b>",
            ) is True
            inst.starttls.assert_called_once()
            inst.login.assert_called_once_with("apikey", "secret")
            inst.send_message.assert_called_once()
        assert smtp_svc.last_attempt["status"] == "sent"


def test_send_uses_smtp_from_env_when_set(monkeypatch):
    from app import app as flask_app, db
    from api.Modules.Notifications.Services import send_email
    _reset_attempt()
    _set_smtp_env(monkeypatch, sender="alerts@dinerobook.com")
    with flask_app.app_context():
        User.query.filter_by(email="t2@example.com").delete()
        db.session.commit()
        with patch("smtplib.SMTP") as smtp_mock:
            inst = MagicMock()
            smtp_mock.return_value.__enter__.return_value = inst
            send_email(
                db.session, "t2@example.com", "S", "B",
            )
            sent_msg = inst.send_message.call_args[0][0]
            assert sent_msg["From"] == "alerts@dinerobook.com"


def test_send_records_failure_status_on_smtp_error(monkeypatch):
    """SMTP exception → status 'failed' + error string captured."""
    from app import app as flask_app, db
    from api.Modules.Notifications.Services import send_email
    from api.Modules.Notifications.Services import smtp as smtp_svc
    _reset_attempt()
    _set_smtp_env(monkeypatch)
    with flask_app.app_context():
        User.query.filter_by(email="t3@example.com").delete()
        db.session.commit()
        with patch("smtplib.SMTP") as smtp_mock:
            smtp_mock.side_effect = OSError("connection refused")
            result = send_email(
                db.session, "t3@example.com", "S", "B",
            )
        assert result is False
        assert smtp_svc.last_attempt["status"] == "failed"
        assert "OSError" in smtp_svc.last_attempt["error"]
        assert "connection refused" in smtp_svc.last_attempt["error"]


def test_send_html_alternative_attached_when_provided(monkeypatch):
    from app import app as flask_app, db
    from api.Modules.Notifications.Services import send_email
    _reset_attempt()
    _set_smtp_env(monkeypatch)
    with flask_app.app_context():
        User.query.filter_by(email="alt@example.com").delete()
        db.session.commit()
        with patch("smtplib.SMTP") as smtp_mock:
            inst = MagicMock()
            smtp_mock.return_value.__enter__.return_value = inst
            send_email(
                db.session, "alt@example.com",
                "S", "Plain body",
                html="<p>Rich body</p>",
            )
            sent_msg = inst.send_message.call_args[0][0]
            assert sent_msg.is_multipart()
            payload = sent_msg.get_payload()
            assert any(
                "<p>Rich body</p>" in p.get_content()
                for p in payload
            )


# ── reset_last_attempt ────────────────────────────────────


def test_reset_last_attempt_clears_state():
    from api.Modules.Notifications.Services import smtp as smtp_svc
    smtp_svc.last_attempt.update({
        "status": "sent", "error": "", "when": datetime.utcnow(),
        "last_to_domain": "x.com", "last_subject": "S",
    })
    smtp_svc.reset_last_attempt()
    assert smtp_svc.last_attempt["status"] == "unknown"
    assert smtp_svc.last_attempt["error"] == ""
    assert smtp_svc.last_attempt["when"] is None
    assert smtp_svc.last_attempt["last_to_domain"] == ""


# ── health_check ──────────────────────────────────────────


def test_health_returns_required_keys():
    from app import app as flask_app, db
    from api.Modules.Notifications.Services import smtp_health_check
    with flask_app.app_context():
        result = smtp_health_check(db.session)
        required = {
            "env", "configured", "status", "error", "when",
            "last_to_domain", "last_subject",
            "recent_events", "last_event_at", "suppressed_count",
        }
        assert required.issubset(set(result.keys()))


def test_health_configured_true_when_required_env_set(monkeypatch):
    from app import app as flask_app, db
    from api.Modules.Notifications.Services import smtp_health_check
    _set_smtp_env(monkeypatch)
    with flask_app.app_context():
        result = smtp_health_check(db.session)
        assert result["configured"] is True
        assert result["env"]["host"] is True
        assert result["env"]["user"] is True
        assert result["env"]["password"] is True


def test_health_configured_false_when_partial(monkeypatch):
    from app import app as flask_app, db
    from api.Modules.Notifications.Services import smtp_health_check
    monkeypatch.delenv("SMTP_HOST", raising=False)
    monkeypatch.delenv("SMTP_USER", raising=False)
    monkeypatch.delenv("SMTP_PASS", raising=False)
    with flask_app.app_context():
        result = smtp_health_check(db.session)
        assert result["configured"] is False


def test_health_aggregates_recent_events():
    from app import app as flask_app, db
    from api.Modules.Notifications.Services import smtp_health_check
    with flask_app.app_context():
        EmailEvent.query.delete()
        db.session.commit()
        # Within the 7-day window
        recent = datetime.utcnow() - timedelta(days=2)
        for evt in ("email.delivered", "email.delivered",
                    "email.bounced"):
            e = EmailEvent(
                event_type=evt, message_id=f"m_{evt}_{recent}",
                created_at=recent,
            )
            db.session.add(e)
        # Outside the 7-day window — should NOT count.
        old = EmailEvent(
            event_type="email.delivered",
            message_id="m_old", created_at=datetime.utcnow()
                - timedelta(days=14),
        )
        db.session.add(old)
        db.session.commit()
        result = smtp_health_check(db.session)
        assert result["recent_events"]["delivered"] == 2
        assert result["recent_events"]["bounced"] == 1
        assert result["recent_events"]["complained"] == 0


def test_health_suppressed_count_includes_bounced_users():
    from app import app as flask_app, db
    from api.Modules.Notifications.Services import smtp_health_check
    with flask_app.app_context():
        User.query.filter(
            User.email.in_([
                "supp1@example.com", "supp2@example.com",
                "active@example.com",
            ]),
        ).delete()
        db.session.commit()
        before = (
            User.query.filter(User.email_bounced_at.isnot(None))
                .count()
        )
        _add_user(db.session, email="supp1@example.com",
                   bounced=True)
        _add_user(db.session, email="supp2@example.com",
                   bounced=True)
        _add_user(db.session, email="active@example.com",
                   bounced=False)
        db.session.flush()
        result = smtp_health_check(db.session)
        assert result["suppressed_count"] >= before + 2


# ── legacy Flask wrappers ─────────────────────────────────


def test_legacy_send_email_delegates(monkeypatch):
    from app import app as flask_app
    from app import _send_email as legacy
    _reset_attempt()
    monkeypatch.delenv("SMTP_HOST", raising=False)
    with flask_app.app_context():
        # Unconfigured → False (no crash)
        assert legacy("x@y.com", "S", "B") is False


def test_legacy_smtp_health_check_delegates():
    from app import app as flask_app
    from app import smtp_health_check as legacy
    with flask_app.app_context():
        result = legacy()
        assert "env" in result
        assert "configured" in result


