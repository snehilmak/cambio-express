import os
# Set test database BEFORE importing app so SQLAlchemy uses it
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-ci")
os.environ.setdefault("STRIPE_SECRET_KEY", "sk_test_fake_key")
os.environ.setdefault("STRIPE_BASIC_PRICE_ID", "price_basic_test")
os.environ.setdefault("STRIPE_PRO_PRICE_ID", "price_pro_test")
os.environ.setdefault("STRIPE_WEBHOOK_SECRET", "whsec_test_secret")
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
# Flask-compatible test client backed by Starlette's TestClient
#
# Production runs every request through ``asgi.py``'s top-level
# ASGI router (FastAPI / SPA / PublicRoutes / cutover / Flask
# fallback). Tests now do too — via Starlette's TestClient sitting
# on the same ``asgi_app``. The wrapper exposes a Flask-test-client-
# compatible surface (``.get/post/...``, ``.get_json()``,
# ``.get_data()``, ``.mimetype``) so test files don't need to
# change to switch transports.
#
# What's gone: the WSGI bridges that used to translate ``/api/v2``,
# ``/app``, PublicRoutes, and cutover into Flask test_client. The
# new client speaks ASGI natively; no a2wsgi in the request path.
from app import app as _flask_app_for_client  # noqa: E402

from starlette.testclient import TestClient as _StarletteTestClient  # noqa: E402


class _HeadersAdapter:
    """Wrap httpx's Headers so it answers werkzeug-style ``getlist``
    in addition to httpx's ``get_list``. The Flask test client
    returns headers that respond to ``getlist`` (single-l); tests
    written against that API expect it."""

    __slots__ = ("_h",)

    def __init__(self, h):
        self._h = h

    def __getitem__(self, key):
        return self._h[key]

    def __contains__(self, key):
        return key in self._h

    def __iter__(self):
        return iter(self._h)

    def __len__(self):
        return len(self._h)

    def get(self, key, default=None):
        return self._h.get(key, default)

    def getlist(self, key):
        return self._h.get_list(key)

    def get_list(self, key):
        return self._h.get_list(key)

    def items(self):
        return self._h.items()

    def keys(self):
        return self._h.keys()

    def values(self):
        return self._h.values()


class AsgiTestResponse:
    """Flask-test-client-compatible response wrapping httpx's response.

    Tests authored for Flask's ``test_client()`` use a small but
    distinctive surface (``.get_json()``, ``.get_data(as_text=...)``,
    ``.mimetype``, ``.status_code``). Mirror it so the migration to
    httpx + ASGITransport is invisible at the call sites.
    """

    __slots__ = ("_resp",)

    def __init__(self, httpx_resp):
        self._resp = httpx_resp

    @property
    def status_code(self) -> int:
        return self._resp.status_code

    @property
    def headers(self):
        return _HeadersAdapter(self._resp.headers)

    @property
    def text(self) -> str:
        return self._resp.text

    @property
    def data(self) -> bytes:
        return self._resp.content

    @property
    def content(self) -> bytes:
        return self._resp.content

    @property
    def mimetype(self) -> str:
        ct = self._resp.headers.get("content-type", "")
        return ct.split(";", 1)[0].strip()

    @property
    def content_type(self) -> str:
        return self._resp.headers.get("content-type", "")

    @property
    def is_json(self) -> bool:
        return self.mimetype == "application/json"

    @property
    def location(self):
        return self._resp.headers.get("location")

    def get_data(self, as_text: bool = False):
        return self._resp.text if as_text else self._resp.content

    def get_json(self):
        try:
            return self._resp.json()
        except Exception:
            return None

    def json(self):
        return self._resp.json()


# Single, session-scoped Starlette TestClient that drives the
# production ASGI app. Spun up at import time so its anyio portal
# + lifespan setup happen once; tests share it through the
# ``AsgiTestClient`` wrapper below.
from asgi import asgi_app as _asgi_app  # noqa: E402

_starlette_client = _StarletteTestClient(_asgi_app)
_starlette_client.__enter__()  # spin up the portal + lifespan


class AsgiTestClient:
    """Flask-test-client-compatible client that runs requests
    through the production ``asgi:asgi_app``.

    Surface kept intentionally narrow — only the methods + kwargs
    historical tests use:

      * ``get`` / ``post`` / ``put`` / ``patch`` / ``delete`` / ``head``
        / ``options``
      * ``headers`` dict, ``json`` body, ``data`` form body, raw
        ``content`` body
      * ``follow_redirects`` (Flask flag name; mapped to httpx's
        ``follow_redirects``)
      * ``query_string`` (Flask flag; appended to the path)

    ``application`` returns the live Flask app for the (now
    shrinking) tests that need ``app_context()`` for direct DB
    work. ``session_transaction()`` is removed — the SPA-cutover
    redirects don't depend on the Flask session, and tests that
    need auth use the JWT login helpers further down.
    """

    application = _flask_app_for_client

    def _request(self, method: str, path: str, *,
                 headers=None, json=None, data=None, content=None,
                 follow_redirects: bool = False,
                 query_string=None, **_extra):
        if query_string:
            if isinstance(query_string, dict):
                from urllib.parse import urlencode
                qs = urlencode(query_string, doseq=True)
            else:
                qs = str(query_string)
            sep = "&" if "?" in path else "?"
            path = f"{path}{sep}{qs}"
        kwargs = {"headers": headers, "follow_redirects": follow_redirects}
        if json is not None:
            kwargs["json"] = json
        if data is not None:
            kwargs["data"] = data
        if content is not None:
            kwargs["content"] = content
        return AsgiTestResponse(
            _starlette_client.request(method, path, **kwargs),
        )

    def get(self, path, **kwargs):
        return self._request("GET", path, **kwargs)

    def post(self, path, **kwargs):
        return self._request("POST", path, **kwargs)

    def put(self, path, **kwargs):
        return self._request("PUT", path, **kwargs)

    def patch(self, path, **kwargs):
        return self._request("PATCH", path, **kwargs)

    def delete(self, path, **kwargs):
        return self._request("DELETE", path, **kwargs)

    def head(self, path, **kwargs):
        return self._request("HEAD", path, **kwargs)

    def options(self, path, **kwargs):
        return self._request("OPTIONS", path, **kwargs)


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
    exists on `store_id`) and return the JWT."""
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


def login_employee(client, store_id: int, username: str,
                   password: str = "x") -> str:
    """Log in as an employee user already seeded by the caller."""
    return client.post(
        "/api/v2/auth/login",
        json={"username": username, "password": password,
              "store_id": store_id},
    ).get_json()["access_token"]


def login_owner(client, username: str,
                password: str = "ownerpass123") -> str:
    """Log in as an owner user (store_id=None — owners aren't
    pinned to a single store) and return the JWT."""
    return client.post(
        "/api/v2/auth/login",
        json={"username": username, "password": password,
              "store_id": None},
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
    return AsgiTestClient()


@pytest.fixture
def logged_in_client():
    """Drop-in for the legacy fixture — returns an
    ``AsgiTestClient``. The SPA-cutover redirects every test
    using this fixture asserts on are unauthenticated, so no
    real login is needed. Tests that need a bearer JWT call
    ``login_admin(client, store_id)`` explicitly."""
    return AsgiTestClient()


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
    """Return ``(client, jwt)`` for a fresh employee user at
    ``store_id``. Replaces the legacy Flask-session variant with a
    real JWT — tests using this pair the client with bearer-auth
    headers when hitting /api/v2/*."""
    from api.Modules.Tenancy.Models import User
    with flask_app.app_context():
        username = f"{username_suffix}_{store_id}_{os.urandom(2).hex()}@test.com"
        emp = User(
            store_id=store_id, username=username,
            full_name="Test Employee", role="employee",
        )
        emp.set_password("x")
        db.session.add(emp)
        db.session.commit()
    c = AsgiTestClient()
    jwt = login_employee(c, store_id, username)
    return c, jwt


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
