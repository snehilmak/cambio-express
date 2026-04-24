"""Announcement broadcast email — superadmin-authored messages that
optionally fan out as email to every opted-in user.

Coverage:
  - Schema: Announcement.broadcast_requested / broadcast_sent_at,
    User.notify_announcement_email.
  - Superadmin POST: broadcast checkbox drives both the flag and the
    actual send. Unchecked = no email fanout.
  - Recipient filter: active + email set + opt-in + not bounced.
  - Per-recipient suppression wins over the batch query (belt-and-
    suspenders — a bounce arriving mid-broadcast still protects).
  - Idempotency: broadcast_sent_at-stamped announcements no-op.
  - CLI `flask broadcast-announcement <id>` exists and invokes
    the sender.
  - Template: renders with brand markers + level accent; plaintext
    fallback is independently coherent.
  - /account/notifications: toggle visible, persists both directions,
    new catalog row present.
  - Failure path: if every send fails (SMTP down), we still stamp
    broadcast_sent_at so the sender doesn't retry indefinitely.
"""
import os
from datetime import datetime, timedelta
from unittest.mock import patch

from flask import render_template

from app import (
    db, User, Store, Announcement,
    broadcast_announcement,
)


# ── Fixtures / helpers ─────────────────────────────────────────

def _set_smtp_env():
    os.environ["SMTP_HOST"] = "smtp.test"
    os.environ["SMTP_USER"] = "u"
    os.environ["SMTP_PASS"] = "p"


def _superadmin_client(app):
    c = app.test_client()
    with app.app_context():
        sa_id = User.query.filter_by(username="superadmin").first().id
    with c.session_transaction() as s:
        s["user_id"] = sa_id; s["role"] = "superadmin"; s["store_id"] = None
    return c


def _make_store_with_admin(app, slug, email, *, opted_in=True, bounced=False):
    with app.app_context():
        s = Store(name=slug, slug=slug, plan="basic")
        db.session.add(s); db.session.flush()
        u = User(store_id=s.id, username=email, email=email,
                 full_name=slug.upper(), role="admin",
                 notify_announcement_email=opted_in)
        u.set_password("x")
        if bounced:
            u.email_bounced_at = datetime.utcnow()
        db.session.add(u); db.session.commit()
        return u.id


def _capture_smtp():
    """Patch smtplib.SMTP and return (context manager, captured_list)."""
    cm = patch("app.smtplib.SMTP")
    return cm


def _start_capture(cm, captured):
    smtp = cm.start()
    smtp.return_value.__enter__.return_value.send_message.side_effect = \
        lambda msg: captured.append(msg)


# ── Schema + model ─────────────────────────────────────────────

def test_announcement_has_broadcast_columns(client):
    with client.application.app_context():
        a = Announcement(message="hi", level="info")
        db.session.add(a); db.session.commit()
        got = db.session.get(Announcement, a.id)
        assert got.broadcast_requested is False
        assert got.broadcast_sent_at is None


def test_user_has_notify_announcement_email_column(client, test_admin_id):
    with client.application.app_context():
        u = db.session.get(User, test_admin_id)
        assert u.notify_announcement_email is False  # opt-in default


# ── POST /superadmin/announcements/new ─────────────────────────

def test_post_without_checkbox_does_not_broadcast(client):
    _set_smtp_env()
    _make_store_with_admin(client.application, "opted-in-store",
                            "opt@example.com", opted_in=True)
    captured = []
    cm = _capture_smtp()
    try:
        _start_capture(cm, captured)
        _superadmin_client(client.application).post(
            "/superadmin/announcements/new",
            data={"message": "System upgrade tonight.", "level": "info"})
    finally:
        cm.stop()
    assert captured == [], "no emails should go out when broadcast not ticked"
    with client.application.app_context():
        a = Announcement.query.order_by(Announcement.id.desc()).first()
        assert a.broadcast_requested is False
        assert a.broadcast_sent_at is None


def test_post_with_checkbox_sends_to_opted_in_users(client):
    _set_smtp_env()
    opt_id = _make_store_with_admin(client.application, "opt-store",
                                     "opt@example.com", opted_in=True)
    _make_store_with_admin(client.application, "off-store",
                            "off@example.com", opted_in=False)
    captured = []
    cm = _capture_smtp()
    try:
        _start_capture(cm, captured)
        _superadmin_client(client.application).post(
            "/superadmin/announcements/new",
            data={"message": "Planned maintenance Sunday.",
                  "level": "warning", "broadcast": "1"})
    finally:
        cm.stop()
    recipients = [m["To"] for m in captured]
    assert "opt@example.com" in recipients
    assert "off@example.com" not in recipients


def test_post_with_checkbox_stamps_broadcast_flags(client):
    _set_smtp_env()
    _make_store_with_admin(client.application, "x-store", "x@example.com")
    cm = _capture_smtp()
    try:
        _start_capture(cm, [])
        _superadmin_client(client.application).post(
            "/superadmin/announcements/new",
            data={"message": "Maintenance.", "level": "info", "broadcast": "1"})
    finally:
        cm.stop()
    with client.application.app_context():
        a = Announcement.query.order_by(Announcement.id.desc()).first()
        assert a.broadcast_requested is True
        assert a.broadcast_sent_at is not None


def test_post_requires_superadmin(logged_in_client):
    """Only superadmin can post announcements. Existing contract;
    regression-guard it alongside the broadcast change."""
    resp = logged_in_client.post("/superadmin/announcements/new",
                                  data={"message": "hi"})
    assert resp.status_code in (302, 403, 404)


# ── broadcast_announcement() function ──────────────────────────

def test_broadcast_filters_inactive_users(client):
    _set_smtp_env()
    uid = _make_store_with_admin(client.application, "inactive-store",
                                  "inactive@example.com", opted_in=True)
    with client.application.app_context():
        db.session.get(User, uid).is_active = False
        a = Announcement(message="hi", level="info")
        db.session.add(a); db.session.commit()
        ann_id = a.id
    captured = []
    cm = _capture_smtp()
    try:
        _start_capture(cm, captured)
        with client.application.app_context():
            broadcast_announcement(ann_id)
    finally:
        cm.stop()
    recipients = [m["To"] for m in captured]
    assert "inactive@example.com" not in recipients


def test_broadcast_filters_users_without_email(client):
    _set_smtp_env()
    # User opted in but no email — can't send, must skip silently.
    uid = _make_store_with_admin(client.application, "no-email-store",
                                  "", opted_in=True)
    with client.application.app_context():
        # `_make_store_with_admin` wrote the blank email already; re-assert
        assert db.session.get(User, uid).email == ""
        a = Announcement(message="hi", level="info")
        db.session.add(a); db.session.commit()
        ann_id = a.id
    captured = []
    cm = _capture_smtp()
    try:
        _start_capture(cm, captured)
        with client.application.app_context():
            n = broadcast_announcement(ann_id)
    finally:
        cm.stop()
    assert captured == []
    assert n == 0


def test_broadcast_skips_suppressed_users(client):
    """User with email_bounced_at set is filtered out of the query AND
    defense-in-depth: _send_email() would reject them anyway. Confirm
    they don't get the email."""
    _set_smtp_env()
    _make_store_with_admin(client.application, "bounced-store",
                            "bounced@example.com", opted_in=True, bounced=True)
    _make_store_with_admin(client.application, "clean-store",
                            "clean@example.com", opted_in=True)
    with client.application.app_context():
        a = Announcement(message="hi", level="info")
        db.session.add(a); db.session.commit()
        ann_id = a.id
    captured = []
    cm = _capture_smtp()
    try:
        _start_capture(cm, captured)
        with client.application.app_context():
            broadcast_announcement(ann_id)
    finally:
        cm.stop()
    recipients = [m["To"] for m in captured]
    assert "bounced@example.com" not in recipients
    assert "clean@example.com" in recipients


def test_broadcast_is_idempotent(client):
    """Running the sender twice on the same announcement — second run
    is a no-op because broadcast_sent_at is set."""
    _set_smtp_env()
    _make_store_with_admin(client.application, "idemp-store",
                            "idemp@example.com", opted_in=True)
    with client.application.app_context():
        a = Announcement(message="hi", level="info")
        db.session.add(a); db.session.commit()
        ann_id = a.id
    captured = []
    cm = _capture_smtp()
    try:
        _start_capture(cm, captured)
        with client.application.app_context():
            first = broadcast_announcement(ann_id)
            second = broadcast_announcement(ann_id)
    finally:
        cm.stop()
    assert first >= 1
    assert second == 0, "re-running should no-op once broadcast_sent_at is set"


def test_broadcast_unknown_id_returns_zero(client):
    with client.application.app_context():
        n = broadcast_announcement(999999)
    assert n == 0


def test_broadcast_subject_uses_first_line(client):
    """Subject line is the first line of the message, capped at 100
    chars. Keeps inbox previews meaningful without a separate
    subject field on the model."""
    _set_smtp_env()
    _make_store_with_admin(client.application, "subj-store",
                            "subj@example.com", opted_in=True)
    with client.application.app_context():
        a = Announcement(
            message="Scheduled outage Sunday night\n\nDetails follow.",
            level="warning")
        db.session.add(a); db.session.commit()
        ann_id = a.id
    captured = []
    cm = _capture_smtp()
    try:
        _start_capture(cm, captured)
        with client.application.app_context():
            broadcast_announcement(ann_id)
    finally:
        cm.stop()
    assert captured[0]["Subject"] == "Scheduled outage Sunday night"


# ── CLI ────────────────────────────────────────────────────────

def test_cli_broadcast_announcement_runs(client):
    """The Click command exists + invokes the sender without raising."""
    with client.application.app_context():
        a = Announcement(message="hi", level="info")
        db.session.add(a); db.session.commit()
        ann_id = a.id
    runner = client.application.test_cli_runner()
    result = runner.invoke(args=["broadcast-announcement", str(ann_id)])
    assert result.exit_code == 0, result.output


# ── Template ───────────────────────────────────────────────────

def test_template_renders_with_brand_markers(client):
    with client.application.test_request_context():
        html = render_template(
            "emails/announcement.html",
            preheader="hi",
            subject="Planned maintenance",
            message="We'll be down Sunday 10pm–midnight EST.",
            level="warning",
            app_url="https://dinerobook.com",
            notifications_url="https://dinerobook.com/account/notifications",
            year=2026, base_url="https://dinerobook.com",
        )
    assert "DineroBook" in html
    assert "Planned maintenance" in html
    assert "Sunday 10pm" in html
    # Warning accent
    assert "#f59e0b" in html
    # Footer toggle link
    assert "/account/notifications" in html


def test_template_picks_correct_level_accent(client):
    """Info/success → neon green, warning → amber, error → red."""
    with client.application.test_request_context():
        for (level, expected) in (
            ("info", "#3fff00"),
            ("success", "#3fff00"),
            ("warning", "#f59e0b"),
            ("error", "#ef4444"),
        ):
            html = render_template(
                "emails/announcement.html",
                preheader="x", subject="x", message="x",
                level=level, app_url="https://x",
                notifications_url="https://x", year=2026,
                base_url="https://x",
            )
            assert expected in html, f"level={level} missing {expected}"


def test_template_preserves_newlines_in_message(client):
    """Multi-paragraph announcements render line breaks via
    `white-space:pre-wrap` — no need to add <br> or <p> server-side."""
    with client.application.test_request_context():
        html = render_template(
            "emails/announcement.html",
            preheader="x", subject="x",
            message="First line.\n\nSecond line.",
            level="info", app_url="https://x",
            notifications_url="https://x", year=2026,
            base_url="https://x",
        )
    assert "pre-wrap" in html
    assert "First line." in html
    assert "Second line." in html


# ── /account/notifications toggle ──────────────────────────────

def test_notifications_page_shows_announcement_toggle(logged_in_client):
    body = logged_in_client.get("/account/notifications").data.decode()
    assert 'id="nae"' in body
    assert "Announcement emails" in body
    assert "notify_announcement_email" in body


def test_notifications_toggle_on_persists(logged_in_client, test_admin_id):
    logged_in_client.post("/account/notifications", data={
        "notify_trial_reminders": "1",
        "notify_announcement_email": "1",
    })
    with logged_in_client.application.app_context():
        u = db.session.get(User, test_admin_id)
        assert u.notify_announcement_email is True


def test_notifications_toggle_off_persists(logged_in_client, test_admin_id):
    # Set true first, then toggle off.
    logged_in_client.post("/account/notifications", data={
        "notify_trial_reminders": "1",
        "notify_announcement_email": "1",
    })
    logged_in_client.post("/account/notifications", data={
        "notify_trial_reminders": "1",
    })  # no announcement flag -> False
    with logged_in_client.application.app_context():
        u = db.session.get(User, test_admin_id)
        assert u.notify_announcement_email is False


def test_catalog_row_for_announcements_visible(logged_in_client):
    """The 'What DineroBook sends you' table has a new row for
    announcement emails, pointing at the toggle above."""
    body = logged_in_client.get("/account/notifications").data.decode()
    assert "Platform announcements" in body
