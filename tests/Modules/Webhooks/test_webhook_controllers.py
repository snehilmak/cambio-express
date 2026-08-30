"""Controller-level tests for /webhooks/stripe + /webhooks/resend.

Service-level dispatch (``handle_stripe_event``, ``derive_plan_from_price``,
the retention-lifecycle side effects) already has thorough coverage in
``tests/test_webhook_retention.py`` and
``tests/Modules/Billing/test_webhook_handler_service.py``. The
signature-verification helper itself is unit-tested in
``tests/test_email_webhook.py`` (Resend) and
``tests/Modules/Billing/test_webhook_service.py`` (Stripe).

This file targets what those don't: the HTTP-facing plumbing in
``api/Modules/Webhooks/Controllers/__init__.py`` —

  * the ``WebhookEvent`` log row the Stripe route writes on every
    delivery (``signature_err`` / ``ok`` / ``processing_err``)
  * the completely-missing-header case (not just a bad one)
  * the handler-raises-but-still-200 contract
  * the Resend route's malformed-JSON-after-valid-signature branch
"""
import base64
import hashlib
import hmac
import json
import os
from datetime import datetime
from unittest.mock import patch

from api.Modules.Webhooks.Models import WebhookEvent
from tests._app import db, db_session


# ── Stripe: /webhooks/stripe ────────────────────────────────────

def _post_stripe(client, event, sig_header="valid"):
    with patch("stripe.Webhook.construct_event", return_value=event):
        return client.post(
            "/api/v2/webhooks/stripe",
            data=json.dumps(event).encode(),
            headers={"Stripe-Signature": sig_header,
                     "Content-Type": "application/json"},
        )


def test_stripe_missing_signature_header_rejected(client):
    """No Stripe-Signature header at all (not just a bad value) must
    still 400 — the route reads the header via `.get(..., "")`."""
    resp = client.post(
        "/api/v2/webhooks/stripe",
        data=b'{"type":"checkout.session.completed"}',
        headers={"Content-Type": "application/json"},
    )
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "Invalid signature"


def test_stripe_missing_signature_logs_signature_err_row(client):
    with db_session():
        before = db.session.query(WebhookEvent).count()
    resp = client.post(
        "/api/v2/webhooks/stripe",
        data=b'{"type":"checkout.session.completed"}',
        headers={"Content-Type": "application/json"},
    )
    assert resp.status_code == 400
    with db_session():
        rows = db.session.query(WebhookEvent).all()
        assert len(rows) == before + 1
        row = rows[-1]
        assert row.source == "stripe"
        assert row.status == "signature_err"
        assert row.error  # non-empty message preserved for forensics


def test_stripe_valid_event_logs_ok_row_with_event_id_and_type(client):
    event = {
        "id": "evt_test_123",
        "type": "invoice.payment_succeeded",  # unhandled by handle_stripe_event
        "data": {"object": {}},
    }
    resp = _post_stripe(client, event)
    assert resp.status_code == 200
    assert resp.get_json() == {"ok": True}
    with db_session():
        row = db.session.query(WebhookEvent).order_by(WebhookEvent.id.desc()).first()
        assert row.source == "stripe"
        assert row.status == "ok"
        assert row.event_id == "evt_test_123"
        assert row.event_type == "invoice.payment_succeeded"


def test_stripe_handler_exception_still_returns_200_and_logs_processing_err(client):
    """Stripe shouldn't retry-storm a buggy handler: 200 + warning
    payload, but the WebhookEvent row is flipped to processing_err
    with the exception message captured for the Webhook Health page."""
    event = {
        "id": "evt_boom",
        "type": "checkout.session.completed",
        "data": {"object": {"metadata": {}, "customer": "cus_x",
                             "subscription": "sub_x"}},
    }
    with patch(
        "api.Modules.Billing.Services.handle_stripe_event",
        side_effect=RuntimeError("kaboom"),
    ):
        resp = _post_stripe(client, event)
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["ok"] is True
    assert "warning" in body
    with db_session():
        row = db.session.query(WebhookEvent).filter_by(event_id="evt_boom").first()
        assert row is not None
        assert row.status == "processing_err"
        assert "kaboom" in row.error


def test_stripe_bad_signature_does_not_call_handler(client):
    """Signature failure short-circuits before handle_stripe_event —
    a forged payload must never reach business logic."""
    with patch("api.Modules.Billing.Services.handle_stripe_event") as mock_handle:
        resp = client.post(
            "/api/v2/webhooks/stripe",
            data=b'{"type":"customer.subscription.deleted"}',
            headers={"Stripe-Signature": "t=0,v1=deadbeef",
                     "Content-Type": "application/json"},
        )
    assert resp.status_code == 400
    mock_handle.assert_not_called()


# ── Resend: /webhooks/resend ────────────────────────────────────

def _set_resend_secret():
    os.environ["RESEND_WEBHOOK_SECRET"] = "whsec_" + base64.b64encode(
        b"controller-test-secret").decode()


def _resend_secret_bytes():
    s = os.environ["RESEND_WEBHOOK_SECRET"]
    return base64.b64decode(s[len("whsec_"):])


def _sign_resend(body, svix_id="msg_ctrl", ts=None):
    ts = ts or str(int(datetime.utcnow().timestamp()))
    signed = f"{svix_id}.{ts}.".encode() + body
    sig = base64.b64encode(
        hmac.new(_resend_secret_bytes(), signed, hashlib.sha256).digest()
    ).decode()
    return {
        "svix-id": svix_id,
        "svix-timestamp": ts,
        "svix-signature": f"v1,{sig}",
    }


def test_resend_malformed_json_with_valid_signature_returns_400(client):
    """Signature verifies over the raw bytes even if they aren't
    valid JSON — the route must catch the json.loads failure
    separately and 400 rather than 500."""
    _set_resend_secret()
    body = b"not-json-but-signed"
    headers = _sign_resend(body)
    resp = client.post(
        "/api/v2/webhooks/resend", data=body,
        content_type="application/json", headers=headers,
    )
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "Invalid JSON"


def test_resend_missing_secret_env_rejects_even_well_formed_signature(client):
    """No RESEND_WEBHOOK_SECRET configured => verify_resend_signature
    always returns False => 400, regardless of header shape."""
    os.environ["RESEND_WEBHOOK_SECRET"] = ""
    body = json.dumps({"type": "email.sent", "data": {"to": ["a@b.com"]}}).encode()
    resp = client.post(
        "/api/v2/webhooks/resend", data=body,
        content_type="application/json",
        headers={"svix-id": "x", "svix-timestamp":
                 str(int(datetime.utcnow().timestamp())),
                 "svix-signature": "v1,whatever"},
    )
    assert resp.status_code == 400
