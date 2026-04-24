"""Branded HTML email templates + the MIME shape each send produces.

Every customer-facing email (password reset, trial reminder) plus the
superadmin test email uses templates/emails/_base.html as its shell,
and a per-email child template for the body. We cover:

  - Each child template renders without error and contains:
    the DineroBook wordmark, the neon accent color, the footer link
    to /account/notifications, and the expected CTA link.
  - No <img> tags — the brand is text + color only, which renders
    reliably in every client and avoids "images not loaded" defaults.
  - No <style> blocks — Gmail strips them; we rely on inline styles
    only.
  - The three real senders (test / reset / trial) produce a
    multipart/alternative message with BOTH text/plain and text/html
    parts. The plaintext fallback is a deliverability signal and
    a real accessibility path.
  - Backward-compat: _send_email(html=None) still produces a plain
    text/plain-only message, so the contract didn't break for any
    future caller that doesn't want HTML.
"""
from unittest.mock import patch
from datetime import datetime, timedelta
import os
import re

from flask import render_template

from app import db, User, Store, _send_email, send_trial_reminders


def _captured_smtp_messages():
    """Patch helper: return a (patcher, messages) pair. Patcher
    context-manages smtplib.SMTP so `send_message` just appends to the
    list. Every test that wants to inspect a sent message uses this."""
    messages = []
    cm = patch("app.smtplib.SMTP")

    def _patch():
        smtp = cm.start()
        smtp.return_value.__enter__.return_value.send_message.side_effect = \
            lambda msg: messages.append(msg)
        return messages

    def _unpatch():
        cm.stop()
    return _patch, _unpatch, messages


def _superadmin_client_with_email(app, email="sa@example.com"):
    c = app.test_client()
    with app.app_context():
        sa = User.query.filter_by(username="superadmin").first()
        sa.email = email
        db.session.commit()
        sa_id = sa.id
    with c.session_transaction() as s:
        s["user_id"] = sa_id
        s["role"] = "superadmin"
        s["store_id"] = None
    return c


def _set_smtp_env():
    os.environ["SMTP_HOST"] = "smtp.test"
    os.environ["SMTP_USER"] = "u"
    os.environ["SMTP_PASS"] = "p"


# ── Template rendering ─────────────────────────────────────────

def test_test_email_renders_with_brand_markers(client):
    with client.application.test_request_context():
        html = render_template(
            "emails/test.html",
            preheader="Test", to_addr="sa@example.com",
            sent_at="2026-04-24T03:46:24Z",
            sender="no-reply@dinerobook.com",
            year=2026, base_url="https://dinerobook.com",
        )
    assert "DineroBook" in html
    assert "#3fff00" in html, "neon accent color must be present"
    assert "Deliverability test" in html
    assert "sa@example.com" in html
    # Footer link back to preferences
    assert "/account/notifications" in html


def test_password_reset_email_renders_with_link(client):
    with client.application.test_request_context():
        html = render_template(
            "emails/password_reset.html",
            preheader="Reset",
            name="Snehil",
            reset_url="https://dinerobook.com/reset-password/abc",
            year=2026, base_url="https://dinerobook.com",
        )
    assert "DineroBook" in html
    assert "Reset your password" in html
    assert "Snehil" in html, "personalized greeting when name provided"
    assert "https://dinerobook.com/reset-password/abc" in html
    # CTA button exists (macro uses a table cell w/ the neon green bg).
    assert "Set new password" in html


def test_trial_reminder_email_renders_with_fields(client):
    with client.application.test_request_context():
        html = render_template(
            "emails/trial_reminder.html",
            preheader="Trial ends",
            name="Snehil",
            store_name="Acme Cambio",
            trial_end_date="May 1, 2026",
            days=2,
            subscribe_url="https://dinerobook.com/subscribe",
            notifications_url="https://dinerobook.com/account/notifications",
            year=2026, base_url="https://dinerobook.com",
        )
    assert "Your trial ends in 2 days" in html
    assert "Acme Cambio" in html
    assert "May 1, 2026" in html
    assert "https://dinerobook.com/subscribe" in html
    # Extra footer line overrides the base footer_extra block
    assert "Don't want trial reminders" in html


def test_templates_have_no_external_images(client):
    """Brand-by-text-and-color on purpose. External images require
    `<img src>` which most clients block until the recipient clicks
    'Load images' — the inbox preview would look broken."""
    with client.application.test_request_context():
        for tmpl, ctx in (
            ("emails/test.html", dict(to_addr="x@y.z", sent_at="0Z", sender="s")),
            ("emails/password_reset.html", dict(name="X", reset_url="https://x")),
            ("emails/trial_reminder.html", dict(
                name="X", store_name="S", trial_end_date="T", days=1,
                subscribe_url="https://x", notifications_url="https://y")),
        ):
            html = render_template(tmpl, preheader="p", year=2026,
                                    base_url="https://x", **ctx)
            assert "<img" not in html, f"{tmpl} unexpectedly has an <img> tag"


def test_templates_have_no_style_blocks(client):
    """Gmail strips <style> blocks entirely — templates must rely on
    inline styles only. A regression that adds <style>...</style> would
    render beautifully in dev and blank in Gmail."""
    with client.application.test_request_context():
        for tmpl, ctx in (
            ("emails/test.html", dict(to_addr="x@y.z", sent_at="0Z", sender="s")),
            ("emails/password_reset.html", dict(name="X", reset_url="https://x")),
            ("emails/trial_reminder.html", dict(
                name="X", store_name="S", trial_end_date="T", days=1,
                subscribe_url="https://x", notifications_url="https://y")),
        ):
            html = render_template(tmpl, preheader="p", year=2026,
                                    base_url="https://x", **ctx)
            assert "<style" not in html.lower(), \
                f"{tmpl} has a <style> block — Gmail strips these"


# ── MIME shape produced by the three real senders ──────────────

def test_send_test_email_produces_multipart_alternative(client):
    _set_smtp_env()
    c = _superadmin_client_with_email(client.application)
    start, stop, messages = _captured_smtp_messages()
    try:
        start()
        c.post("/superadmin/send-test-email")
    finally:
        stop()
    assert len(messages) == 1
    msg = messages[0]
    assert msg.is_multipart()
    assert msg.get_content_type() == "multipart/alternative"
    parts = sorted(p.get_content_type() for p in msg.iter_parts())
    assert parts == ["text/html", "text/plain"]


def test_send_test_email_html_part_has_brand(client):
    _set_smtp_env()
    c = _superadmin_client_with_email(client.application)
    start, stop, messages = _captured_smtp_messages()
    try:
        start()
        c.post("/superadmin/send-test-email")
    finally:
        stop()
    html = next(p for p in messages[0].iter_parts()
                if p.get_content_type() == "text/html").get_content()
    assert "DineroBook" in html
    assert "#3fff00" in html
    assert "Deliverability test" in html


def test_forgot_password_sends_multipart_alternative(client):
    """Password reset email goes out with BOTH text and HTML parts —
    the HTML part lands in clients that render it, the text part
    survives HTML-stripping clients + is what spam filters score."""
    _set_smtp_env()
    start, stop, messages = _captured_smtp_messages()
    try:
        start()
        client.post("/forgot-password", data={"username": "admin@test.com"})
    finally:
        stop()
    assert len(messages) == 1
    msg = messages[0]
    assert msg.is_multipart()
    types = sorted(p.get_content_type() for p in msg.iter_parts())
    assert types == ["text/html", "text/plain"]
    # Subject is the new one
    assert "Reset your DineroBook password" in msg["Subject"]


def test_forgot_password_html_part_has_reset_link_and_brand(client):
    _set_smtp_env()
    start, stop, messages = _captured_smtp_messages()
    try:
        start()
        client.post("/forgot-password", data={"username": "admin@test.com"})
    finally:
        stop()
    html = next(p for p in messages[0].iter_parts()
                if p.get_content_type() == "text/html").get_content()
    assert "DineroBook" in html
    assert "Reset your password" in html
    # The reset-URL token is randomized; we match the route prefix.
    assert re.search(r'/reset-password/[A-Za-z0-9_\-]+', html), \
        "reset URL missing from HTML body"


def test_trial_reminder_sends_multipart_alternative(client, test_admin_id, test_store_id):
    """End-to-end: put the fixture store into expiring_soon, run the
    sender, and inspect the MIME envelope."""
    _set_smtp_env()
    with client.application.app_context():
        u = db.session.get(User, test_admin_id)
        u.email = "admin@test.com"
        u.notify_trial_reminders = True
        s = db.session.get(Store, test_store_id)
        s.plan = "trial"
        s.trial_ends_at = datetime.utcnow() + timedelta(days=2)
        s.trial_reminder_sent_at = None
        db.session.commit()
    start, stop, messages = _captured_smtp_messages()
    try:
        start()
        with client.application.app_context():
            send_trial_reminders()
    finally:
        stop()
    assert len(messages) == 1
    msg = messages[0]
    assert msg.is_multipart()
    types = sorted(p.get_content_type() for p in msg.iter_parts())
    assert types == ["text/html", "text/plain"]
    html = next(p for p in msg.iter_parts()
                if p.get_content_type() == "text/html").get_content()
    assert "DineroBook" in html
    assert "Your trial ends in" in html


# ── Backward compat: html=None still works ────────────────────

def test_send_email_without_html_produces_plaintext_only(client):
    """A caller who doesn't pass html= gets a simple text/plain
    message, no multipart envelope. Don't break that contract — if
    any future caller wants text-only, they shouldn't be forced to
    carry an HTML template they don't want."""
    _set_smtp_env()
    start, stop, messages = _captured_smtp_messages()
    try:
        start()
        with client.application.test_request_context():
            _send_email("ghost@example.com", "hi", "body only")
    finally:
        stop()
    assert len(messages) == 1
    msg = messages[0]
    assert not msg.is_multipart()
    assert msg.get_content_type() == "text/plain"
    assert msg.get_content().strip() == "body only"


def test_plaintext_part_of_multipart_is_independently_readable(client):
    """Accessibility / spam-score regression: the plaintext alternative
    must be a coherent standalone message, not stripped-of-tags HTML.
    Test by asserting a known plaintext phrase from the reset body
    that never appears in the HTML template."""
    _set_smtp_env()
    start, stop, messages = _captured_smtp_messages()
    try:
        start()
        client.post("/forgot-password", data={"username": "admin@test.com"})
    finally:
        stop()
    text = next(p for p in messages[0].iter_parts()
                if p.get_content_type() == "text/plain").get_content()
    # This exact wording lives only in the plaintext body, not the HTML.
    assert "current password will keep working" in text
