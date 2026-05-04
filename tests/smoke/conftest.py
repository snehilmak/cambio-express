"""Smoke-test infrastructure: a real Flask HTTP server + Playwright.

The unit/integration suite uses Flask's test_client which never executes
JavaScript — that's how silent JS errors in chrome (e.g. owner avatar
dropdown wiring missing the `.is-open` class toggle, search.js loading
deferred while inline scripts depended on it synchronously) shipped to
production. This layer fills the gap by spinning up a real
Werkzeug HTTP server and driving it through a headless Chromium so any
uncaught JS error fails a test.

Design choices:
- Session-scoped server. Cheap to start once, expensive to start per
  test. Tests must not mutate state in ways that break other tests
  (or they should reset within the test).
- Tempfile-based SQLite (NOT in-memory). The threaded server has its
  own connection pool; in-memory SQLite scopes to one connection.
- Browser is also session-scoped. Per-test contexts give isolation.
- The unit-suite conftest's autouse `clean_db` is overridden here
  with a no-op so it doesn't truncate the smoke DB between tests.
- Smoke tests skip themselves if Playwright's Chromium isn't
  installed — they're a strict superset, not a hard requirement.

Run only the smoke layer: `pytest tests/smoke/`
Run everything else:     `pytest tests/ --ignore=tests/smoke`
"""
import os
import socket
import threading
import time

import pytest


# ── Skip the whole module if Playwright/Chromium aren't installed ──
# Treat the smoke layer as opt-in: not every dev environment has the
# browser binaries, and the unit suite must keep working without them.
playwright_module = pytest.importorskip("playwright.sync_api")
sync_playwright = playwright_module.sync_playwright


# ── Override the parent conftest's clean_db autouse fixture ────────
# The unit suite recreates the schema before every test; we want one
# stable DB for the entire smoke session so a real HTTP server can
# share state with the test driver.
@pytest.fixture(autouse=True)
def clean_db():
    yield


def _free_port():
    """Bind+release to discover a free TCP port — avoids a hardcoded
    port collision when the suite runs alongside dev servers."""
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


@pytest.fixture(scope="session")
def smoke_server(tmp_path_factory):
    """Boot Flask in a daemon thread bound to a tempfile SQLite.
    Yields a base URL for Playwright to point at; shuts the server
    down when the session ends."""
    db_path = tmp_path_factory.mktemp("smoke") / "smoke.db"
    # Force the app's DATABASE_URL to our smoke DB. The `app` module
    # is already imported by the parent conftest at this point, so we
    # have to re-bind SQLAlchemy's engine instead of relying on the
    # env var alone. Two-step: set env (so anything that reads it
    # later sees the right value) AND patch app.config + db.engine.
    os.environ["DATABASE_URL"] = f"sqlite:///{db_path}"
    from app import app as flask_app, db
    flask_app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{db_path}"
    flask_app.config["TESTING"] = False  # Real server, not test_client.

    # Re-bind SQLAlchemy to the new URI. The default engine cached
    # the in-memory URI from the parent conftest's import-time set.
    with flask_app.app_context():
        db.engine.dispose()
        db.create_all()
        # Seed the same fixture data the unit conftest creates so
        # our test logins match what the rest of the suite expects.
        from tests.conftest import seed_test_data
        seed_test_data()

    port = _free_port()
    from werkzeug.serving import make_server
    srv = make_server("127.0.0.1", port, flask_app, threaded=True)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    # Spin until the port responds — make_server returns before the
    # listener is fully ready, and Playwright fails fast.
    deadline = time.time() + 5
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                break
        except OSError:
            time.sleep(0.05)
    yield f"http://127.0.0.1:{port}"
    srv.shutdown()


@pytest.fixture(scope="session")
def playwright_session():
    """One Playwright instance per session — starting/stopping it
    has real cost and there's nothing per-test about it."""
    with sync_playwright() as p:
        yield p


@pytest.fixture(scope="session")
def browser(playwright_session):
    """Chromium launched once. Use the `page` fixture for per-test
    isolation — it gives each test a fresh BrowserContext."""
    # Honor PLAYWRIGHT_BROWSERS_PATH if the env set it (the chromium
    # in this dev image lives under /opt/pw-browsers/, not the default
    # ~/.cache location). Playwright reads the env var natively.
    b = playwright_session.chromium.launch(headless=True, args=[
        "--no-sandbox", "--disable-dev-shm-usage",
    ])
    yield b
    b.close()


@pytest.fixture
def page(browser):
    """Per-test page in an isolated BrowserContext (cookies / storage
    don't leak between tests). Captures real JS pageerror events so
    the test body can `assert not js_errors` to fail on silent
    failures.

    `console.error` is intentionally NOT captured: external CDNs
    (jsDelivr fonts, flag-icons CSS) flood that channel with cert /
    network failures in sandboxed test environments, and those
    aren't bugs in our code. `pageerror` only fires for genuine
    uncaught JS exceptions, which is what we care about."""
    ctx = browser.new_context()
    p = ctx.new_page()
    js_errors = []
    p.on("pageerror", lambda e: js_errors.append(str(e)))
    p.js_errors = js_errors  # Tests read this directly.
    yield p
    ctx.close()


def _login_via_form(page, base_url, username, password, store_slug=None):
    """Drive the password-login flow. Used by the role-fixtures below."""
    if store_slug:
        page.goto(f"{base_url}/login?store={store_slug}")
    else:
        page.goto(f"{base_url}/login")
    page.fill("input[name='username']", username)
    page.fill("input[name='password']", password)
    page.click("button[type='submit']")
    # Wait for the post-login redirect to settle. The dashboard is
    # the standard landing for an admin/owner; loading state covers
    # both paths.
    page.wait_for_load_state("networkidle")


@pytest.fixture
def admin_page(page, smoke_server):
    """A `page` already signed in as the seeded test admin."""
    _login_via_form(page, smoke_server,
                     username="admin@test.com",
                     password="testpass123!",
                     store_slug="test-store")
    return page


@pytest.fixture
def owner_page(page, smoke_server):
    """A `page` signed in as a freshly-created owner with one linked
    store. Created on demand inside the smoke DB."""
    from app import app as flask_app, db, User, Store, StoreOwnerLink
    with flask_app.app_context():
        # Idempotent: reuse if a previous test already created this owner.
        existing = User.query.filter_by(username="owner-smoke@x.com").first()
        if existing:
            oid = existing.id
        else:
            o = User(username="owner-smoke@x.com", role="owner",
                     full_name="Smoke Owner", store_id=None)
            o.set_password("smokepass123!")
            db.session.add(o); db.session.commit()
            oid = o.id
            sa_store = Store.query.filter_by(slug="test-store").first()
            db.session.add(StoreOwnerLink(owner_id=oid, store_id=sa_store.id))
            db.session.commit()
    _login_via_form(page, smoke_server,
                     username="owner-smoke@x.com",
                     password="smokepass123!")
    return page
