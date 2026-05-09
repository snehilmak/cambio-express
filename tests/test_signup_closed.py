"""Tests for the SIGNUP_CLOSED feature gate.

When SIGNUP_CLOSED=1, the legacy /signup and /signup/owner forms
render the "invite-only / sign in to existing account" notice
instead of the form, and the FastAPI signup endpoints return 503.
Existing customers can still log in normally.

We don't reload the module — that breaks SQLAlchemy state. Instead
we monkeypatch the module-level constant; the routes read it via
the imported name, so a patch is enough.
"""
import pytest

import app as app_module


@pytest.fixture
def signup_closed():
    """Flip the gate ON for the duration of the test, restore on
    teardown so subsequent tests see the default-OPEN state."""
    original = app_module.SIGNUP_CLOSED
    app_module.SIGNUP_CLOSED = True
    yield
    app_module.SIGNUP_CLOSED = original


def test_signup_get_renders_closed_page_when_flag_on(client, signup_closed):  # noqa: ARG001
    resp = client.get("/signup")
    assert resp.status_code == 200
    body = resp.data.lower()
    assert b"signups are paused" in body or b"invite" in body
    # The form is GONE — no inputs to type into.
    assert b'name="store_name"' not in resp.data


def test_signup_post_blocked_when_flag_on(client, signup_closed):  # noqa: ARG001
    """Even a direct POST is blocked — we don't accidentally create
    accounts via curl while the gate is on."""
    resp = client.post("/signup", data={
        "store_name": "Sneaky", "email": "sneak@example.com",
        "password": "abcdefgh", "phone": "",
    })
    assert resp.status_code == 403
    from app import Store, app as flask_app
    with flask_app.app_context():
        assert Store.query.filter_by(email="sneak@example.com").first() is None


def test_signup_owner_get_renders_closed_page_when_flag_on(client, signup_closed):  # noqa: ARG001
    resp = client.get("/signup/owner")
    assert resp.status_code == 200
    body = resp.data.lower()
    assert b"signups are paused" in body or b"invite" in body
    assert b'name="full_name"' not in resp.data


def test_signup_owner_post_blocked_when_flag_on(client, signup_closed):  # noqa: ARG001
    resp = client.post("/signup/owner", data={
        "full_name": "Sneaky Owner",
        "email": "sneakowner@example.com",
        "password": "abcdefgh",
    })
    assert resp.status_code == 403
    from app import User, app as flask_app
    with flask_app.app_context():
        assert User.query.filter_by(username="sneakowner@example.com").first() is None


def test_api_signup_returns_503_when_flag_on(client, signup_closed):  # noqa: ARG001
    """FastAPI endpoint also gates so an attacker can't bypass via
    the JSON API."""
    resp = client.post("/api/v2/auth/signup", json={
        "store_name": "Sneaky", "email": "sneak@example.com",
        "password": "abcdefgh",
    })
    assert resp.status_code == 503
    body = resp.data.lower()
    assert b"closed" in body or b"sign in" in body


def test_signup_open_by_default(client):
    """Default (no flag flipped) → signups work — GET returns the form."""
    resp = client.get("/signup")
    assert resp.status_code == 200
    assert b'name="store_name"' in resp.data
    assert b"signups are paused" not in resp.data.lower()
