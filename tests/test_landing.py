"""Tests for the legacy `/` URL.

The marketing landing page moved to React (/app/, served by
frontend/src/routes/Landing.tsx). The Flask `/` route is now
a 301 redirect — page-rendering tests would assert against
the deleted Jinja template.

PWA preservation: when an installed-PWA employee opens their
shortcut (which points at `/`), the `ds_last_store` cookie
bounces them to /app/login/<slug> so they land on their
store's sign-in page rather than the marketing pitch.
"""


def test_root_redirects_to_app(client):
    resp = client.get("/", follow_redirects=False)
    assert resp.status_code == 301
    assert resp.headers["Location"] == "/app/"


def test_login_at_new_route(client):
    resp = client.get("/login")
    assert resp.status_code == 200


def test_root_redirects_logged_in_user(logged_in_client):
    """Logged-in users see the same 301 — the SPA's /app/ root
    handles the signed-in bounce internally (Landing.tsx renders
    the same marketing page; Sign in nav goes to /app/login → JWT
    in localStorage promotes to /app/dashboard)."""
    resp = logged_in_client.get("/", follow_redirects=False)
    assert resp.status_code == 301
    assert resp.headers["Location"] == "/app/"


def test_root_with_pwa_cookie_bounces_to_store_login(client, test_store_id):
    """PWA preservation: an installed-PWA employee with the
    `ds_last_store` cookie set hits / and gets bounced to their
    store's SPA login page rather than the marketing landing.
    Without this, an employee on a chromeless PWA install would
    have no way to type the URL back to their store."""
    from app import Store, app as flask_app, db
    with flask_app.app_context():
        s = db.session.get(Store, test_store_id)
        slug = s.slug
    client.set_cookie("ds_last_store", slug)
    resp = client.get("/", follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["Location"] == f"/app/login/{slug}"


def test_store_has_trial_columns(client):
    """Store model must have trial_ends_at and grace_ends_at columns."""
    with client.application.app_context():
        from app import Store
        s = Store.query.filter_by(slug="test-store").first()
        assert hasattr(s, "trial_ends_at")
        assert hasattr(s, "grace_ends_at")
        assert s.trial_ends_at is not None
        assert s.grace_ends_at is not None
