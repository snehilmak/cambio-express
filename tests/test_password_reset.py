"""Tests for the legacy /forgot-password and /reset-password Flask routes.

Both routes were retired in favour of the React SPA (/app/forgot-password,
/app/reset-password) which submits to /api/v2/auth/forgot-password +
/api/v2/auth/reset-password. The Flask stubs that remain are 301
redirects so old reset emails (still in users' inboxes) and any
url_for() calls in still-Jinja templates keep working.

Token contract + email send + security invariants are tested under
the FastAPI controller — see:

  tests/Modules/Auth/test_auth_controllers.py
    test_forgot_password_always_returns_ok_for_unknown_email
    test_forgot_password_issues_token_for_known_user
    test_forgot_password_response_does_not_leak_token
    test_reset_password_round_trip
    test_reset_password_rejects_invalid_token
    test_reset_password_rejects_expired_token
    test_reset_password_rejects_mismatched_confirm
    test_reset_password_rejects_short_new_password
    test_reset_password_consumed_token_cannot_be_reused

  tests/Modules/Auth/test_password_reset_service.py
    sha256-only storage of the raw token, single-use, employee /
    superadmin / inactive-account exclusions
"""


def test_forgot_password_redirects_to_spa(client):
    resp = client.get("/forgot-password", follow_redirects=False)
    assert resp.status_code == 301
    assert resp.headers["Location"] == "/app/forgot-password"


def test_forgot_password_post_also_redirects(client):
    """An old form/PWA POSTing to /forgot-password gets bounced.
    Body content is dropped — the SPA owns submission via JSON now."""
    resp = client.post(
        "/forgot-password", data={"username": "owner@example.com"},
        follow_redirects=False,
    )
    assert resp.status_code == 301
    assert resp.headers["Location"] == "/app/forgot-password"


def test_reset_password_path_token_redirects_with_query_param(client):
    """Old emails link to /reset-password/<token>; we hand the token
    off to the SPA via ?token= so it still works."""
    raw = "abcdef0123456789"
    resp = client.get(f"/reset-password/{raw}", follow_redirects=False)
    assert resp.status_code == 301
    assert resp.headers["Location"] == f"/app/reset-password?token={raw}"


def test_reset_password_post_with_path_token_also_redirects(client):
    """If a stale browser tab POSTs the old form, we still 301 it
    forward (the body is lost — SPA owns submission)."""
    raw = "tokens-from-an-old-tab"
    resp = client.post(
        f"/reset-password/{raw}",
        data={"password": "newpass123!", "confirm_password": "newpass123!"},
        follow_redirects=False,
    )
    assert resp.status_code == 301
    assert resp.headers["Location"] == f"/app/reset-password?token={raw}"
