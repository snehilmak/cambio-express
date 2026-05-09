"""Tests for the legacy /signup Flask route.

The legacy GET form + POST handler were retired in favour of the
React /app/signup page, which submits to /api/v2/auth/signup
directly. The legacy route is preserved as a 301 redirect so
old bookmarks, external links, and `url_for('signup')` calls in
still-Jinja templates keep resolving. Form-validation +
store-creation tests live in tests/Modules/Auth/test_auth_controllers.py
and tests/Modules/Auth/test_signup_service.py.
"""


def test_signup_redirects_to_spa(client):
    resp = client.get("/signup", follow_redirects=False)
    assert resp.status_code == 301
    assert resp.headers["Location"] == "/app/signup"


def test_signup_preserves_ref_query_string(client):
    resp = client.get("/signup?ref=ABCD1234", follow_redirects=False)
    assert resp.status_code == 301
    assert resp.headers["Location"] == "/app/signup?ref=ABCD1234"


def test_signup_preserves_plan_query_string(client):
    resp = client.get("/signup?plan=basic", follow_redirects=False)
    assert resp.status_code == 301
    assert resp.headers["Location"] == "/app/signup?plan=basic"


def test_signup_post_also_redirects(client):
    """An old form that POSTs to /signup also gets redirected to
    the SPA. The redirect doesn't carry the form body — but the
    SPA owns submission now so this case only matters for stale
    browser tabs holding the old Jinja form."""
    resp = client.post("/signup", data={
        "store_name": "Old Form",
        "email": "old@example.com",
        "password": "securepass1!",
    }, follow_redirects=False)
    assert resp.status_code == 301
    assert resp.headers["Location"] == "/app/signup"
