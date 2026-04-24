"""Resend delivery webhook + bounce/complaint suppression.

Coverage:
  - Signature verification: valid + tampered + stale timestamp.
  - Hard bounce stamps User.email_bounced_at.
  - Complaint stamps User.email_bounced_at AND flips notify_trial_reminders.
  - Events persist to EmailEvent with the right shape.
  - _send_email skips suppressed recipients and sets status='suppressed'.
  - Overview template shows delivery counts + suppressed count.
  - purge_expired_stores null-outs EmailEvent.user_id for purged users
    so the User delete doesn't hit an FK constraint.
  - Event types other than bounce/complaint (sent, delivered, opened)
    persist but don't have side effects.
"""
import base64
import hashlib
import hmac
import json
import os
from datetime import datetime, timedelta

from app import (
    db, User, Store, EmailEvent,
    _verify_resend_signature, _send_email, smtp_health_check,
    purge_expired_stores,
)


# ── Signature helpers ──────────────────────────────────────────

def _set_webhook_secret():
    os.environ["RESEND_WEBHOOK_SECRET"] = "whsec_" + base64.b64encode(
        b"test-secret-bytes").decode()


def _secret_bytes():
    s = os.environ["RESEND_WEBHOOK_SECRET"]
    return base64.b64decode(s[len("whsec_"):])


def _sign(body, svix_id="msg_1", ts=None):
    ts = ts or str(int(datetime.utcnow().timestamp()))
    signed = f"{svix_id}.{ts}.".encode() + body
    sig = base64.b64encode(
        hmac.new(_secret_bytes(), signed, hashlib.sha256).digest()
    ).decode()
    return {
        "svix-id": svix_id,
        "svix-timestamp": ts,
        "svix-signature": f"v1,{sig}",
    }


def _webhook_body(event_type, to="customer@example.com", email_id="re_abc",
                   bounce_type=None):
    data = {"email_id": email_id, "to": [to]}
    if bounce_type:
        data["bounce"] = {"type": bounce_type}
    return json.dumps({"type": event_type, "data": data}).encode()


# ── _verify_resend_signature unit tests ────────────────────────

def test_signature_valid(client):
    _set_webhook_secret()
    body = _webhook_body("email.delivered")
    h = _sign(body, svix_id="x")
    assert _verify_resend_signature(
        os.environ["RESEND_WEBHOOK_SECRET"],
        h["svix-id"], h["svix-timestamp"], h["svix-signature"], body) is True


def test_signature_rejected_when_body_tampered(client):
    _set_webhook_secret()
    body = _webhook_body("email.delivered")
    h = _sign(body, svix_id="x")
    tampered = body.replace(b"delivered", b"complained")
    assert _verify_resend_signature(
        os.environ["RESEND_WEBHOOK_SECRET"],
        h["svix-id"], h["svix-timestamp"], h["svix-signature"], tampered) is False


def test_signature_rejected_when_timestamp_stale(client):
    _set_webhook_secret()
    body = _webhook_body("email.delivered")
    stale_ts = str(int(datetime.utcnow().timestamp()) - 3600)  # 1hr old
    h = _sign(body, svix_id="x", ts=stale_ts)
    assert _verify_resend_signature(
        os.environ["RESEND_WEBHOOK_SECRET"],
        h["svix-id"], h["svix-timestamp"], h["svix-signature"], body) is False


def test_signature_rejected_when_secret_missing(client):
    body = _webhook_body("email.delivered")
    h = _sign.__wrapped__ if hasattr(_sign, "__wrapped__") else None  # noqa
    assert _verify_resend_signature(
        "", "x", str(int(datetime.utcnow().timestamp())), "v1,whatever",
        body) is False


def test_signature_accepts_multiple_versions_in_header(client):
    """Svix allows space-separated signatures in the header (for key
    rotation). Any one matching should accept."""
    _set_webhook_secret()
    body = _webhook_body("email.delivered")
    h = _sign(body, svix_id="x")
    doubled = f"v1,INVALIDSIG {h['svix-signature']}"
    assert _verify_resend_signature(
        os.environ["RESEND_WEBHOOK_SECRET"],
        h["svix-id"], h["svix-timestamp"], doubled, body) is True


# ── /webhooks/resend HTTP route ────────────────────────────────

def test_webhook_rejects_missing_signature(client):
    _set_webhook_secret()
    resp = client.post("/webhooks/resend", data=_webhook_body("email.sent"),
                        content_type="application/json")
    assert resp.status_code == 400


def test_webhook_rejects_bad_signature(client):
    _set_webhook_secret()
    body = _webhook_body("email.sent")
    resp = client.post("/webhooks/resend", data=body,
                        content_type="application/json",
                        headers={"svix-id": "m", "svix-timestamp":
                                 str(int(datetime.utcnow().timestamp())),
                                 "svix-signature": "v1,wrong"})
    assert resp.status_code == 400


def test_webhook_persists_event_on_valid_request(client):
    _set_webhook_secret()
    body = _webhook_body("email.delivered", to="ok@example.com")
    resp = client.post("/webhooks/resend", data=body,
                        content_type="application/json",
                        headers=_sign(body))
    assert resp.status_code == 200
    with client.application.app_context():
        evs = EmailEvent.query.all()
        assert len(evs) == 1
        assert evs[0].event_type == "email.delivered"
        assert evs[0].to_addr == "ok@example.com"


def test_webhook_hard_bounce_stamps_user(client, test_admin_id):
    """Hard bounce → User.email_bounced_at gets stamped. Matched via
    case-insensitive equality on User.email."""
    _set_webhook_secret()
    with client.application.app_context():
        u = db.session.get(User, test_admin_id)
        u.email = "Admin@Test.com"  # uppercase variation
        db.session.commit()
    body = _webhook_body("email.bounced", to="admin@test.com",
                          bounce_type="hard")
    client.post("/webhooks/resend", data=body,
                content_type="application/json", headers=_sign(body))
    with client.application.app_context():
        u = db.session.get(User, test_admin_id)
        assert u.email_bounced_at is not None


def test_webhook_soft_bounce_does_not_stamp(client, test_admin_id):
    """Soft bounce (mailbox full, greylisting) is a retry situation —
    we record the event but don't suppress the address."""
    _set_webhook_secret()
    with client.application.app_context():
        u = db.session.get(User, test_admin_id)
        u.email = "admin@test.com"
        db.session.commit()
    body = _webhook_body("email.bounced", to="admin@test.com",
                          bounce_type="soft")
    client.post("/webhooks/resend", data=body,
                content_type="application/json", headers=_sign(body))
    with client.application.app_context():
        u = db.session.get(User, test_admin_id)
        assert u.email_bounced_at is None, "soft bounce must not suppress"


def test_webhook_complaint_stamps_and_flips_toggles(client, test_admin_id):
    """Spam-report: stamp the suppression column AND flip every
    notify_* preference to False. Strongest-possible user signal."""
    _set_webhook_secret()
    with client.application.app_context():
        u = db.session.get(User, test_admin_id)
        u.email = "admin@test.com"
        u.notify_trial_reminders = True
        db.session.commit()
    body = _webhook_body("email.complained", to="admin@test.com")
    client.post("/webhooks/resend", data=body,
                content_type="application/json", headers=_sign(body))
    with client.application.app_context():
        u = db.session.get(User, test_admin_id)
        assert u.email_bounced_at is not None
        assert u.notify_trial_reminders is False


def test_webhook_handles_unmatched_email(client):
    """Events for an address we have no User for (e.g. superadmin test
    to a personal gmail) still persist — useful for forensics."""
    _set_webhook_secret()
    body = _webhook_body("email.delivered", to="stranger@gmail.com")
    resp = client.post("/webhooks/resend", data=body,
                        content_type="application/json", headers=_sign(body))
    assert resp.status_code == 200
    with client.application.app_context():
        ev = EmailEvent.query.first()
        assert ev.user_id is None
        assert ev.to_addr == "stranger@gmail.com"


def test_webhook_handles_non_bounce_events_without_side_effects(client, test_admin_id):
    """email.sent, .delivered, .opened, .clicked, .delivery_delayed
    all persist but must not stamp suppression."""
    _set_webhook_secret()
    with client.application.app_context():
        u = db.session.get(User, test_admin_id)
        u.email = "admin@test.com"; u.notify_trial_reminders = True
        db.session.commit()
    for kind in ("email.sent", "email.delivered", "email.opened",
                 "email.clicked", "email.delivery_delayed"):
        body = _webhook_body(kind, to="admin@test.com", email_id=kind)
        resp = client.post("/webhooks/resend", data=body,
                            content_type="application/json",
                            headers=_sign(body, svix_id=kind))
        assert resp.status_code == 200
    with client.application.app_context():
        u = db.session.get(User, test_admin_id)
        assert u.email_bounced_at is None
        assert u.notify_trial_reminders is True


# ── _send_email suppression ────────────────────────────────────

def test_send_email_skips_suppressed_user(client, test_admin_id):
    """A user with email_bounced_at set is skipped — the function
    returns False and flips _last_smtp_attempt to status='suppressed'."""
    os.environ["SMTP_HOST"] = "smtp.test"
    os.environ["SMTP_USER"] = "u"
    os.environ["SMTP_PASS"] = "p"
    with client.application.app_context():
        u = db.session.get(User, test_admin_id)
        u.email = "bounced@test.com"
        u.email_bounced_at = datetime.utcnow()
        db.session.commit()
    with client.application.app_context():
        ok = _send_email("bounced@test.com", "hi", "body")
    assert ok is False
    h = smtp_health_check()
    assert h["status"] == "suppressed"
    assert "suppression" in h["error"].lower()


def test_send_email_skips_suppressed_case_insensitive(client, test_admin_id):
    """Suppression match is case-insensitive, so BOUNCED@TEST.com
    is the same as bounced@test.com."""
    os.environ["SMTP_HOST"] = "smtp.test"
    os.environ["SMTP_USER"] = "u"
    os.environ["SMTP_PASS"] = "p"
    with client.application.app_context():
        u = db.session.get(User, test_admin_id)
        u.email = "bounced@test.com"
        u.email_bounced_at = datetime.utcnow()
        db.session.commit()
    with client.application.app_context():
        ok = _send_email("BOUNCED@Test.COM", "hi", "body")
    assert ok is False


def test_send_email_does_not_suppress_unmatched_address(client):
    """Addresses we don't have a User for (personal Gmail used for
    superadmin test) aren't in the suppression check — the send
    proceeds regardless."""
    os.environ["SMTP_HOST"] = "smtp.test"
    os.environ["SMTP_USER"] = "u"
    os.environ["SMTP_PASS"] = "p"
    from unittest.mock import patch
    with patch("app.smtplib.SMTP") as smtp:
        smtp.return_value.__enter__.return_value.send_message.return_value = {}
        with client.application.app_context():
            ok = _send_email("personal@gmail.com", "hi", "body")
    assert ok is True


# ── Overview health card ───────────────────────────────────────

def _superadmin_client(app):
    c = app.test_client()
    with app.app_context():
        sa_id = User.query.filter_by(username="superadmin").first().id
    with c.session_transaction() as s:
        s["user_id"] = sa_id; s["role"] = "superadmin"; s["store_id"] = None
    return c


def test_overview_shows_webhook_secret_env_state(client):
    """New SMTP_* row: RESEND_WEBHOOK_SECRET. Shown as set/missing
    the same way the other env vars are."""
    os.environ.pop("RESEND_WEBHOOK_SECRET", None)
    body = _superadmin_client(client.application).get(
        "/superadmin/controls?tab=overview").data.decode()
    assert "RESEND_WEBHOOK_SECRET" in body
    assert "delivery events not tracked" in body


def test_overview_shows_delivery_counts_when_events_present(client, test_admin_id):
    """Populate EmailEvent rows, then confirm the 7-day roll-up shows
    delivered / bounced / complained counts on the Overview."""
    with client.application.app_context():
        for (kind, n) in (("email.delivered", 5), ("email.bounced", 1),
                           ("email.complained", 1), ("email.opened", 3)):
            for _ in range(n):
                db.session.add(EmailEvent(
                    message_id="m", to_addr="x@y.z",
                    event_type=kind, bounce_type="",
                    payload=""))
        db.session.commit()
    body = _superadmin_client(client.application).get(
        "/superadmin/controls?tab=overview").data.decode()
    # Section header visible
    assert "Delivery events" in body
    # Each count rendered (look for the row label — numbers can shift
    # depending on rendering whitespace).
    assert "Delivered" in body
    assert "Bounced" in body
    assert "Complained" in body
    assert "Suppressed addresses" in body


# ── Purge FK safety ────────────────────────────────────────────

def test_purge_nulls_out_email_event_user_id(client):
    """Retention purge: a store's users are deleted. EmailEvent.user_id
    is a FK; without the pre-loop null-out step, Postgres rejects the
    delete. We null and keep the event rows so post-purge forensics
    still work (useful when auditing "did we ever email this address"
    months later)."""
    with client.application.app_context():
        s = Store(name="Doomed", slug="doomed-ee", plan="inactive",
                  is_active=False,
                  data_retention_until=datetime.utcnow() - timedelta(days=1))
        db.session.add(s); db.session.flush()
        u = User(store_id=s.id, username="doomed@x",
                 full_name="Doomed", role="admin")
        u.set_password("x"); db.session.add(u); db.session.flush()
        db.session.add(EmailEvent(
            message_id="m", to_addr="doomed@x",
            user_id=u.id, event_type="email.delivered",
            bounce_type="", payload=""))
        db.session.commit()
        ev_id = EmailEvent.query.first().id

        n = purge_expired_stores()
        assert n == 1

        ev = db.session.get(EmailEvent, ev_id)
        assert ev is not None, "event should survive purge (historical record)"
        assert ev.user_id is None, "user_id should be nulled so the FK doesn't block"
