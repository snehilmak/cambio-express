import os
# Set test database BEFORE importing app so SQLAlchemy uses it
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-ci")
os.environ.setdefault("STRIPE_SECRET_KEY", "sk_test_fake_key")
os.environ.setdefault("STRIPE_BASIC_PRICE_ID", "price_basic_test")
os.environ.setdefault("STRIPE_PRO_PRICE_ID", "price_pro_test")
os.environ.setdefault("STRIPE_WEBHOOK_SECRET", "whsec_test_secret")
# Default the SPA cutover redirects OFF in tests so the existing
# legacy-route assertions keep working unchanged. Tests that want
# to exercise the cutover layer opt in via the `cutover_on` /
# `cutover_off` fixtures defined in tests/test_spa_cutover.py.
# Production / CI deploy honours the real flag (default on).
os.environ["SPA_CUTOVER_ENABLED"] = "0"
# Disable rate limiting in tests — the in-memory bucket persists
# across tests in a single session, so the second test that calls
# /login would 429 instantly. Tests that exercise the limiter
# itself spawn a subprocess with the env var flipped on (see
# tests/test_rate_limiting.py). Force-set (not setdefault) so a
# stray RATELIMIT_ENABLED=1 in the shell can't break CI.
os.environ["RATELIMIT_ENABLED"] = "0"

import pytest
from datetime import date, datetime, timedelta

# Speed up the test suite by downgrading werkzeug's password hashing to
# 1 PBKDF2 iteration. Production uses the default 600,000 — deliberately
# slow to defeat brute force — but tests don't need that, and before this
# the suite spent roughly 12s inside set_password calls alone. MUST run
# before `from app import ...` because app binds `generate_password_hash`
# at import time via `from werkzeug.security import generate_password_hash`.
import werkzeug.security as _wsec
_ORIG_HASH = _wsec.generate_password_hash
_wsec.generate_password_hash = lambda pw, method="pbkdf2:sha256:1", salt_length=8: (
    _ORIG_HASH(pw, method=method, salt_length=salt_length)
)

from app import app as flask_app, db

flask_app.config["TESTING"] = True


# ─────────────────────────────────────────────────────────────
# FastAPI TestClient leak plug
#
# Bare `TestClient(api_app)` instances (~189 call sites across
# ~11 test files) skip the recommended context-manager form, so
# FastAPI's lifespan + httpx Session never get cleanly shut
# down. The leftover asyncio coroutines hang on as "Task pending"
# warnings and — when GC'd mid-test — rollback the SQLAlchemy
# session of whatever test happens to be running. That used to
# produce 50/50 flakes on tests like
# test_webhook_persists_event_on_valid_request.
#
# Fix: monkey-patch TestClient to register every instance for
# teardown. The autouse `_close_fastapi_clients` fixture below
# closes them all between tests, draining the pending tasks
# before they can interfere with the next test.
#
# This eliminates the need to refactor the 189 call sites
# individually — they keep working unchanged. Removing this
# block is safe once those sites all use `with TestClient(...)
# as c:` form.
import fastapi.testclient as _fastapi_testclient
_OrigTestClient = _fastapi_testclient.TestClient
_open_fastapi_clients: list = []


class _AutoCloseTestClient(_OrigTestClient):
    """Drop-in TestClient that registers itself with the autouse
    fixture for guaranteed teardown after each test."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _open_fastapi_clients.append(self)


_fastapi_testclient.TestClient = _AutoCloseTestClient
# Also re-export under fastapi.testclient module attr so re-imports
# pick up the patched version even after fastapi/starlette internal
# caching.
import sys as _sys
if "fastapi.testclient" in _sys.modules:
    _sys.modules["fastapi.testclient"].TestClient = _AutoCloseTestClient


@pytest.fixture(autouse=True)
def _close_fastapi_clients():
    """After each test, walk the list of TestClient instances
    created during the test and exit them properly. Each `__exit__`
    closes httpx + drains FastAPI's lifespan tasks so the next
    test starts with a clean asyncio state."""
    yield
    while _open_fastapi_clients:
        c = _open_fastapi_clients.pop()
        try:
            c.__exit__(None, None, None)
        except Exception:
            # Don't let a single client teardown failure mask the
            # actual test result; keep popping.
            pass


# ─────────────────────────────────────────────────────────────
# /api/v2 dispatch in tests — bypass the leaky a2wsgi bridge.
#
# Production routes /api/v2/* through asgi.py's native ASGI
# dispatcher (see asgi.py + render.yaml). The Flask app's
# DispatcherMiddleware mount via a2wsgi.ASGIMiddleware is only
# kept on the Flask side as a strangler-fig fallback that
# production NEVER hits — but the test suite uses Flask's
# WSGI test_client, which routes through that legacy mount.
#
# Under coverage's tracer the a2wsgi-spawned asyncio.Task objects
# get GC'd while still flagged "pending" — Python emits
# "Task was destroyed but it is pending!" and rolls back the
# SQLAlchemy session of whatever test happens to be running.
# Manifestation: random 500 Internal Server Errors on
# /api/v2/monthly PUT in test_bank_charges_pl.py and similar.
#
# Fix: replace the /api/v2 mount with a TestClient-backed WSGI
# bridge. starlette TestClient uses anyio.from_thread.start_
# blocking_portal — well-defined task lifecycle, no leaks under
# coverage. Production behaviour is unaffected; asgi.py already
# bypasses a2wsgi for /api/v2/* (PR #399).
from werkzeug.middleware.dispatcher import DispatcherMiddleware as _DM
from a2wsgi import ASGIMiddleware as _A2W


def _make_testclient_bridge(asgi_app):
    """Build a WSGI handler that funnels requests into ``asgi_app``
    via a starlette ``TestClient``. anyio's blocking-portal gives a
    well-defined task lifecycle that the leaky ``a2wsgi`` bridge
    doesn't — see the long comment above the call site. The
    returned handler conforms to the WSGI app signature so it can
    replace an ``ASGIMiddleware`` in the dispatcher mounts dict."""
    # Use _OrigTestClient (unpatched starlette class) so the bridge's
    # client is NOT registered with the autouse close-between-tests
    # fixture above. The bridge stays alive for the full session.
    tc = _OrigTestClient(asgi_app)
    tc.__enter__()  # spin up the portal + lifespan task

    def _wsgi_handler(environ, start_response):
        # Translate WSGI environ → httpx request → response →
        # WSGI iterable. anyio's portal handles the ASGI roundtrip.
        method = environ["REQUEST_METHOD"]
        path = environ.get("PATH_INFO", "/")
        qs = environ.get("QUERY_STRING", "")
        url = path + ("?" + qs if qs else "")
        body = b""
        cl = environ.get("CONTENT_LENGTH")
        if cl and int(cl) > 0:
            body = environ["wsgi.input"].read(int(cl))
        headers: dict[str, str] = {}
        for k, v in environ.items():
            if k.startswith("HTTP_"):
                hdr = k[5:].replace("_", "-").lower()
                headers[hdr] = v
        ct = environ.get("CONTENT_TYPE")
        if ct:
            headers["content-type"] = ct
        if cl:
            headers["content-length"] = cl
        # Never follow redirects at this layer — Flask's
        # ``test_client(follow_redirects=…)`` flag isn't part of the
        # WSGI environ. If we let httpx auto-follow, the outer
        # Flask client never sees the 301 and tests asserting on
        # the redirect status fail (was a real bug — see
        # ``tests/test_spa_shell.py::test_legacy_root_redirects_to_app``).
        resp = tc.request(method, url, headers=headers, content=body,
                          follow_redirects=False)
        status_line = f"{resp.status_code} {resp.reason_phrase or ''}".strip()
        out_headers = [(k, v) for k, v in resp.headers.items()
                       if k.lower() != "transfer-encoding"]
        start_response(status_line, out_headers)
        return [resp.content]

    return _wsgi_handler


def _swap_in_testclient_bridge() -> None:
    """Swap both ASGIMiddleware mounts (``/api/v2`` and ``/app``) for
    TestClient-backed handlers. Idempotent — safe to call once at
    module import."""
    bridge = flask_app.wsgi_app
    if not isinstance(bridge, _DM):
        return
    for mount_prefix in ("/api/v2", "/app"):
        asgi_mw = bridge.mounts.get(mount_prefix)
        if asgi_mw is None or not isinstance(asgi_mw, _A2W):
            continue
        bridge.mounts[mount_prefix] = _make_testclient_bridge(asgi_mw.app)


_swap_in_testclient_bridge()


# Public-route bridge: asgi.py dispatches a handful of root-mounted
# paths (``/``, ``/privacy``, ``/sw.js``, ``/offline``, ``/tv/*``,
# ``/api/tv-pair/*``) to the Starlette ``api.PublicRoutes.public_app``
# rather than Flask. The Flask ``test_client`` doesn't know about
# asgi.py, so those paths would 404 inside the tests. Wrap
# ``flask_app.wsgi_app`` with a thin pre-router that mirrors asgi.py's
# decision and forwards matching paths to a TestClient bridge.
from api.PublicRoutes import (
    PUBLIC_ROUTE_PATHS as _PUBLIC_PATHS,
    PUBLIC_ROUTE_PREFIXES as _PUBLIC_PREFIXES,
    public_app as _public_app,
)


def _install_public_routes_bridge() -> None:
    public_bridge = _make_testclient_bridge(_public_app)
    inner = flask_app.wsgi_app

    def _wsgi_router(environ, start_response):
        path = environ.get("PATH_INFO", "")
        if path in _PUBLIC_PATHS or any(
            path.startswith(p) for p in _PUBLIC_PREFIXES
        ):
            return public_bridge(environ, start_response)
        return inner(environ, start_response)

    flask_app.wsgi_app = _wsgi_router


_install_public_routes_bridge()


# Stable TOTP secret for the seeded superadmin so test helpers can
# compute current codes deterministically via `pyotp.TOTP().now()`.
# Picked once at module import; never rotated within a session.
import pyotp as _pyotp
SUPERADMIN_TOTP_SECRET = _pyotp.random_base32()


def login_superadmin(client) -> str:
    """Log in as the seeded superadmin and return the access token.
    Wraps the two-step SPA flow (password → TOTP exchange) so tests
    don't have to repeat the `pyotp.TOTP(secret).now()` boilerplate.
    Returns the bearer JWT ready for `Authorization: Bearer <…>`."""
    pending = client.post(
        "/api/v2/auth/login",
        json={
            "username": "superadmin",
            "password": "super2025!",
            "store_id": None,
        },
    ).get_json()["pending_token"]
    code = _pyotp.TOTP(SUPERADMIN_TOTP_SECRET).now()
    return client.post(
        "/api/v2/auth/login/totp",
        json={"pending_token": pending, "code": code},
    ).get_json()["access_token"]


def login_admin(client, store_id: int) -> str:
    """Log in as the seeded admin@test.com user (or whatever admin
    exists on `store_id`) and return the JWT. Used by CSV-export
    tests that need a real bearer token rather than the legacy
    Flask cookie session."""
    from api.Modules.Tenancy.Models import User
    with flask_app.app_context():
        u = (
            User.query
            .filter_by(store_id=store_id, role="admin")
            .first()
        )
        assert u is not None, (
            f"No admin user on store_id={store_id} — did seed run?"
        )
        username = u.username
    return client.post(
        "/api/v2/auth/login",
        json={
            "username": username, "password": "testpass123!",
            "store_id": store_id,
        },
    ).get_json()["access_token"]


def seed_test_data():
    from api.Modules.Tenancy.Models import Store, User
    from api.Modules.TVDisplay.Services.seed import seed_catalogs
    from app import db
    # TV-display catalogs (companies + banks) are seeded by init_db
    # in production but the test fixture drop_all/create_all cycle
    # resets every table — we rebuild them here so picker UI tests
    # see the same canonical 12 + 34 entries production does.
    seed_catalogs(db.session)
    if not User.query.filter_by(username="superadmin", store_id=None).first():
        # Pre-enrol the seeded superadmin so SPA login returns a real
        # access_token directly via the TOTP exchange step. The flow
        # is: POST /auth/login with creds → pending_token → POST
        # /auth/login/totp with `pyotp.TOTP(SUPERADMIN_TOTP_SECRET).now()`
        # → access_token. Tests use the `login_superadmin(client)`
        # helper below to wrap that two-step exchange. See CLAUDE.md
        # invariant #13 — production superadmins MUST be enrolled.
        sa = User(username="superadmin", full_name="Platform Owner",
                  role="superadmin", store_id=None,
                  totp_secret=SUPERADMIN_TOTP_SECRET,
                  totp_enrolled_at=datetime.utcnow())
        sa.set_password("super2025!")
        db.session.add(sa)
    if not Store.query.filter_by(slug="test-store").first():
        s = Store(name="Test Store", slug="test-store",
                  email="admin@test.com", plan="trial")
        # trial columns added in Task 2 — set them if available
        if hasattr(Store, "trial_ends_at"):
            s.trial_ends_at = datetime.utcnow() + timedelta(days=7)
        if hasattr(Store, "grace_ends_at"):
            s.grace_ends_at = datetime.utcnow() + timedelta(days=11)
        db.session.add(s)
        db.session.flush()
        a = User(store_id=s.id, username="admin@test.com",
                 full_name="Test Admin", role="admin")
        a.set_password("testpass123!")
        db.session.add(a)
    db.session.commit()


@pytest.fixture(autouse=True)
def clean_db():
    with flask_app.app_context():
        # Defensive cleanup: bare FastAPI TestClient instances in many
        # tests leak pending asyncio tasks ("Task was destroyed but it
        # is pending!") that hold references to SQLAlchemy sessions
        # and silently rollback this test's seed. See the comment in
        # .github/workflows/ci.yml for the full backstory. Until the
        # 189 TestClient call sites are refactored to use `with`
        # blocks, force a session.remove() at start so any leaked
        # session is detached before we drop+create+seed.
        db.session.remove()
        db.drop_all()
        db.create_all()
        seed_test_data()
        # Verify seed actually persisted — if a leaked async task
        # rolled back the seed transaction, the row is gone before
        # the test even starts. Retry once to make CI deterministic.
        from api.Modules.Tenancy.Models import Store
        if Store.query.filter_by(slug="test-store").first() is None:
            db.session.remove()
            db.drop_all()
            db.create_all()
            seed_test_data()
        yield
        db.session.remove()


@pytest.fixture
def client():
    return flask_app.test_client()


@pytest.fixture
def logged_in_client():
    """Client pre-authenticated as the test store admin."""
    c = flask_app.test_client()
    with flask_app.app_context():
        from api.Modules.Tenancy.Models import User
        u = User.query.filter_by(username="admin@test.com").first()
        assert u is not None, "admin@test.com user not found — did seed_test_data run?"
        uid, sid = u.id, u.store_id
    with c.session_transaction() as sess:
        sess["user_id"] = uid
        sess["role"] = "admin"
        sess["store_id"] = sid
    return c


# ─────────────────────────────────────────────────────────────
# Shared test helpers
#
# Multiple test files were reinventing the same "find the test store",
# "log me in as an employee", and "seed a transfer row" helpers. Pulled
# the common ones here so new tests don't have to copy-paste.
# ─────────────────────────────────────────────────────────────

@pytest.fixture
def test_store_id():
    """The Store.id of the seeded test-store fixture row."""
    from api.Modules.Tenancy.Models import Store
    with flask_app.app_context():
        return Store.query.filter_by(slug="test-store").first().id


@pytest.fixture
def test_admin_id():
    """The User.id of the seeded admin@test.com user."""
    from api.Modules.Tenancy.Models import User
    with flask_app.app_context():
        return User.query.filter_by(username="admin@test.com").first().id


def make_employee_client(store_id, *, username_suffix="emp"):
    """Return a Flask test client authenticated as a new employee user
    at the given store. Each call creates a fresh User row so tests
    that need multiple employees can call this multiple times."""
    from api.Modules.Tenancy.Models import User
    c = flask_app.test_client()
    with flask_app.app_context():
        emp = User(
            store_id=store_id,
            username=f"{username_suffix}_{store_id}_{os.urandom(2).hex()}@test.com",
            full_name="Test Employee",
            role="employee",
        )
        emp.set_password("x")
        db.session.add(emp)
        db.session.commit()
        uid = emp.id
    with c.session_transaction() as sess:
        sess["user_id"] = uid
        sess["role"] = "employee"
        sess["store_id"] = store_id
    return c


def seed_transfer(store_id, creator_id, *, send_date=None,
                  sender_name="Jane Doe", send_amount=500.0, fee=5.0,
                  company="Intermex", service_type="Money Transfer",
                  status="Sent"):
    """Seed a single Transfer row directly (no form POST). Returns the
    new transfer's id. federal_tax follows the default 1% rate —
    callers that need a specific tax value can .query the row and
    override after."""
    from api.Modules.Transfers.Models import Transfer
    with flask_app.app_context():
        t = Transfer(
            store_id=store_id,
            created_by=creator_id,
            send_date=send_date or date.today(),
            company=company,
            service_type=service_type,
            sender_name=sender_name,
            send_amount=send_amount,
            fee=fee,
            federal_tax=round(send_amount * 0.01, 2),
            commission=0.0,
            status=status,
        )
        db.session.add(t)
        db.session.commit()
        return t.id
