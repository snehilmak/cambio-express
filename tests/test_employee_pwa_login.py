"""Employee-login-from-installed-PWA recovery path.

Installed PWAs launch at manifest.start_url ("/") with the address bar
hidden — so an employee whose session has expired lands on the generic
/login page with no way to type their store URL. The fix is two-part:

1. A `ds_last_store` cookie set whenever someone visits their store's
   login page (or types their store code on the escape hatch). While
   that cookie is present, `/` and `/login` auto-redirect to
   `/login/<slug>`.
2. An /employee-login POST endpoint on the generic page that turns a
   typed store code into a redirect (and sets the cookie).
"""
from app import app as flask_app, db


COOKIE = "ds_last_store"


def _get_cookie(client, name):
    # Flask's test client exposes cookies via cookie_jar on older werkzeug
    # and client.get_cookie on newer. Fall back through both.
    getter = getattr(client, "get_cookie", None)
    if getter:
        c = getter(name) or getter(name, domain="localhost")
        return c.value if c else None
    for c in getattr(client, "cookie_jar", []):
        if c.name == name:
            return c.value
    return None


def _set_cookie(client, name, value):
    setter = getattr(client, "set_cookie", None)
    # Newer werkzeug: client.set_cookie(key, value, domain=...)
    # Older werkzeug: client.set_cookie(server_name, key, value)
    try:
        setter(name, value, domain="localhost")
    except TypeError:
        setter("localhost", name, value)


# ── Cookie is set on the store login page ────────────────────

def test_store_login_get_sets_last_store_cookie(client):
    """The legacy /login/<slug> form is now a 301 to /app/login/<slug>
    (React route). We still set the `ds_last_store` cookie on the
    redirect so the installed-PWA bounce path on `/` and `/login`
    keeps working unchanged."""
    resp = client.get("/login/test-store", follow_redirects=False)
    assert resp.status_code == 301
    assert resp.headers["Location"] == "/app/login/test-store"
    assert _get_cookie(client, COOKIE) == "test-store"


# ── Cookie bounces `/` and `/login` to the store login ───────

def test_root_redirects_to_store_login_when_cookie_set(client):
    _set_cookie(client, COOKIE, "test-store")
    resp = client.get("/", follow_redirects=False)
    assert resp.status_code == 302
    assert "/login/test-store" in resp.headers["Location"]


def test_login_redirects_to_store_login_when_cookie_set(client):
    # Diagnostic: query DB state BEFORE and AFTER the request to see
    # whether seed worked at all and whether the request cleared it.
    from app import Store
    with flask_app.app_context():
        before = [(s.id, s.slug, s.is_active) for s in Store.query.all()]
    _set_cookie(client, COOKIE, "test-store")
    resp = client.get("/login", follow_redirects=False)
    if resp.status_code != 302:
        with flask_app.app_context():
            after = [(s.id, s.slug, s.is_active) for s in Store.query.all()]
        cookies = [(c.name, c.value)
                   for c in getattr(client, "cookie_jar", [])]
        raise AssertionError(
            f"expected 302, got {resp.status_code}; "
            f"location={resp.headers.get('Location')!r}; "
            f"stores_before={before!r}; "
            f"stores_after={after!r}; "
            f"cookies_on_client={cookies!r}; "
            f"body_first_400={resp.data[:400]!r}"
        )
    assert "/login/test-store" in resp.headers["Location"]


def test_root_ignores_cookie_for_unknown_slug(client):
    _set_cookie(client, COOKIE, "does-not-exist")
    resp = client.get("/", follow_redirects=False)
    # No redirect — the landing page still renders.
    assert resp.status_code == 200


# ── Employee POST on /login leaves a cookie breadcrumb ───────

def test_employee_post_on_main_login_sets_last_store_cookie(client):
    from app import User, Store
    with flask_app.app_context():
        s = Store.query.filter_by(slug="test-store").first()
        emp = User(store_id=s.id, username="emp_pwa@test.com",
                   full_name="Emp PWA", role="employee")
        emp.set_password("emppass123!")
        db.session.add(emp)
        db.session.commit()
    resp = client.post("/login", data={
        "username": "emp_pwa@test.com", "password": "emppass123!"
    })
    assert resp.status_code == 200
    assert _get_cookie(client, COOKIE) == "test-store"
    # And the error message steers them to the escape hatch.
    body = resp.data.lower()
    assert b"store" in body


# ── /employee-login escape hatch ─────────────────────────────

def test_employee_login_redirect_valid_slug(client):
    resp = client.post("/employee-login",
                       data={"store_code": "test-store"},
                       follow_redirects=False)
    assert resp.status_code == 302
    assert "/login/test-store" in resp.headers["Location"]
    assert _get_cookie(client, COOKIE) == "test-store"


def test_employee_login_redirect_valid_slug_case_insensitive(client):
    resp = client.post("/employee-login",
                       data={"store_code": "  TEST-STORE  "},
                       follow_redirects=False)
    assert resp.status_code == 302
    assert "/login/test-store" in resp.headers["Location"]


def test_employee_login_redirect_unknown_slug_shows_error(client):
    resp = client.post("/employee-login",
                       data={"store_code": "not-a-real-store"})
    assert resp.status_code == 200
    assert b"couldn&#39;t find" in resp.data or b"couldn't find" in resp.data
