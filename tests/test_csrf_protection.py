"""CSRF protection regression tests.

Validates the Flask-WTF CSRFProtect wiring in app.py + the
`csrf.exempt(...)` carve-outs for webhook + WebAuthn JSON routes.

The conftest sets `WTF_CSRF_ENABLED=False` so the rest of the
suite (which posts to /login, /admin/settings/*, etc. without
minting a token) keeps working. These tests temporarily re-enable
the kill-switch and assert:

  - POST to a protected route WITHOUT a `csrf_token` form field
    returns 400 (CSRF failure).
  - POST to the same route WITH a valid token succeeds.
  - POST to an exempted route (Stripe webhook, passkey JSON)
    succeeds without a token.

Add a case here when:
  - A new Flask form-POST route is added — verify it rejects no-token
    POSTs.
  - A new csrf.exempt() target lands in app.py — verify it accepts
    no-token POSTs.
"""
from __future__ import annotations

import pytest

from app import app as flask_app


@pytest.fixture
def csrf_enabled():
    """Flip Flask-WTF's CSRF enforcement back on for this test
    only. Tears down in `finally` so a failed assertion can't leak
    CSRF=True to a later test."""
    prior = flask_app.config.get("WTF_CSRF_ENABLED", False)
    flask_app.config["WTF_CSRF_ENABLED"] = True
    try:
        yield
    finally:
        flask_app.config["WTF_CSRF_ENABLED"] = prior


def _mint_token(client):
    """Hit a GET route that renders a CSRF-protected form so the
    session is seeded with a token, then pull the token out of
    the response HTML. Re-use across tests."""
    # /login is always reachable to an unauthenticated client and
    # renders {{ csrf_token() }} in its form.
    r = client.get("/login")
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    # Token field looks like:
    #   <input type="hidden" name="csrf_token" value="ABC123..."
    marker = 'name="csrf_token" value="'
    idx = body.find(marker)
    assert idx >= 0, "csrf_token input not found on /login"
    start = idx + len(marker)
    end = body.find('"', start)
    return body[start:end]


def test_csrf_blocks_post_without_token(csrf_enabled):
    """A POST to /login without a `csrf_token` should be rejected
    with 400 (the Flask-WTF default for CSRF failure)."""
    c = flask_app.test_client()
    r = c.post(
        "/login",
        data={"username": "x@y.z", "password": "wrong"},
    )
    assert r.status_code == 400, r.status_code


def test_csrf_allows_post_with_valid_token(csrf_enabled):
    """A POST carrying the token from the same session should
    succeed (the route may still flash an auth error, but the
    HTTP code won't be 400)."""
    c = flask_app.test_client()
    token = _mint_token(c)
    r = c.post(
        "/login",
        data={
            "csrf_token": token,
            "username": "nope@nowhere.test",
            "password": "wrong",
        },
    )
    # Login fails (no such user) but CSRF passed — we get the
    # error-rendered login page (200) or a redirect, NOT 400.
    assert r.status_code != 400, r.status_code


def test_stripe_webhook_exempted_from_csrf(csrf_enabled):
    """`csrf.exempt(stripe_webhook)` should let a webhook POST
    through without a token. The handler then 400s on bad
    signature, but that's a different error path."""
    c = flask_app.test_client()
    r = c.post(
        "/webhooks/stripe",
        data="{}",
        headers={"Stripe-Signature": "t=1,v1=bad"},
    )
    # Whatever the webhook returns (400 bad-signature, 401, etc.),
    # it should NOT be 400 specifically due to CSRF (Flask-WTF's
    # CSRF-failure body is "The CSRF token is missing.").
    body = r.get_data(as_text=True)
    assert "CSRF" not in body, body[:200]


def test_resend_webhook_exempted_from_csrf(csrf_enabled):
    c = flask_app.test_client()
    r = c.post(
        "/webhooks/resend",
        json={"type": "email.delivered"},
    )
    body = r.get_data(as_text=True)
    assert "CSRF" not in body, body[:200]


def test_passkey_login_begin_exempted_from_csrf(csrf_enabled):
    """WebAuthn passkey ceremonies POST JSON; CSRF tokens add no
    value when the client has to prove a valid session anyway.
    Exempted via csrf.exempt(...) in app.py."""
    c = flask_app.test_client()
    r = c.post(
        "/login/passkey/begin",
        json={},
    )
    body = r.get_data(as_text=True)
    assert "CSRF" not in body, body[:200]


def test_csrf_config_is_on_in_prod_off_in_tests():
    """The conftest forces WTF_CSRF_ENABLED=False so the rest of
    the suite keeps working. Regression guard for the
    `os.environ["WTF_CSRF_ENABLED"] = "False"` line in
    conftest.py."""
    assert flask_app.config["WTF_CSRF_ENABLED"] is False
