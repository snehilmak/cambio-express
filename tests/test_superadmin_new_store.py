"""Legacy /superadmin/stores/new redirect tests.

The create-store form moved to /app/superadmin/stores/new (React),
backed by POST /api/v2/superadmin/stores. The full create + audit
+ duplicate-slug + admin-user-seed coverage now lives in
tests/Modules/Superadmin/test_stores_endpoint.py.

This file only proves the legacy URL still 301s for both verbs —
GET (bookmarked link) and POST (any in-flight Jinja form) — and
that the role gate stays in place.
"""
from app import app as flask_app


def _superadmin_client():
    """Fresh Flask client authenticated as the seeded superadmin."""
    from app import User
    c = flask_app.test_client()
    with flask_app.app_context():
        sa = User.query.filter_by(username="superadmin", store_id=None).first()
        uid = sa.id
    with c.session_transaction() as sess:
        sess["user_id"] = uid
        sess["role"] = "superadmin"
    return c


_VALID_FORM = {
    "name": "New Branch",
    "slug": "new-branch",
    "email": "branch@example.com",
    "phone": "555-0000",
    "address": "1 Main St",
    "plan": "trial",
    "admin_username": "branchadmin",
    "admin_name": "Branch Admin",
    "admin_password": "branchpass123!",
}


def test_legacy_get_redirects_to_spa():
    c = _superadmin_client()
    resp = c.get("/superadmin/stores/new", follow_redirects=False)
    assert resp.status_code == 301
    assert resp.headers["Location"].endswith("/app/superadmin/stores/new")


def test_legacy_post_redirects_to_spa():
    """POST 301 — the SPA form submits to /api/v2 directly. Any
    in-flight Jinja form gets bounced rather than silently failing."""
    c = _superadmin_client()
    resp = c.post(
        "/superadmin/stores/new",
        data=_VALID_FORM, follow_redirects=False,
    )
    assert resp.status_code == 301
    assert resp.headers["Location"].endswith("/app/superadmin/stores/new")


def test_unauthenticated_new_store_redirects_to_login(client):
    resp = client.post(
        "/superadmin/stores/new", data=_VALID_FORM, follow_redirects=False,
    )
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]


def test_store_admin_cannot_create_store(logged_in_client):
    resp = logged_in_client.post(
        "/superadmin/stores/new", data=_VALID_FORM, follow_redirects=False,
    )
    # superadmin_required kicks an admin out — either to / login or
    # to dashboard. Either way the response must NOT be a 301 to the
    # SPA form, which would be a privilege escalation.
    assert resp.status_code in (302, 403)
    if resp.status_code == 302:
        assert "/superadmin" not in resp.headers["Location"]
