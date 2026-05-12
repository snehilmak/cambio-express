"""Session-cookie hardening config invariants.

Regression guard for the "Before going live" security item that
sets HTTPOnly / SameSite=Lax on every environment and Secure=True
on HTTPS prod. Three things we don't want a future refactor to
silently flip:

  - SESSION_COOKIE_HTTPONLY must stay True (or the cookie becomes
    readable from JS and a single XSS exfils every signed-in user).
  - SESSION_COOKIE_SAMESITE must stay "Lax" (or every cross-site
    POST becomes a CSRF target).
  - SESSION_COOKIE_SECURE must be True when APP_BASE_URL points at
    HTTPS, False otherwise (preserves dev / CI / sqlite ergonomics
    while keeping prod cookies on the encrypted channel).

The test reads the live `flask_app.config` mutated by the
production code path — no monkeypatching — so it catches the
config wiring as it actually runs.
"""
from app import app as flask_app


def test_session_cookie_httponly_is_true():
    assert flask_app.config["SESSION_COOKIE_HTTPONLY"] is True


def test_session_cookie_samesite_is_lax():
    assert flask_app.config["SESSION_COOKIE_SAMESITE"] == "Lax"


def test_session_cookie_secure_off_in_dev():
    # tests/conftest.py does not set APP_BASE_URL, so the test
    # environment is treated as dev. SESSION_COOKIE_SECURE must be
    # False or sessions silently fail to set over HTTP.
    assert flask_app.config["SESSION_COOKIE_SECURE"] is False


def test_permanent_session_lifetime_bounded():
    # A bounded lifetime keeps a forgotten signed-in laptop from
    # being a permanent key to the kingdom. 7 days is the current
    # ceiling; change deliberately and update this test.
    from datetime import timedelta
    assert flask_app.config["PERMANENT_SESSION_LIFETIME"] == (
        timedelta(days=7)
    )
