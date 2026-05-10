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
# a2wsgi.ASGIMiddleware leak pin
#
# The Flask test_client → DispatcherMiddleware → ASGIMiddleware →
# FastAPI dispatch path is wired up at app import time. Unlike
# TestClient, a2wsgi reuses a single shared event-loop thread for
# every request and creates an asyncio.Task per call via
# ``loop.create_task(self.app(...))``. When a request finishes,
# the task is `done()`, but its done-callback chain (through
# ASGIResponder) holds the task object weakly — under coverage's
# C-tracer the GC walks the call graph more aggressively and the
# Task's ``__del__`` fires while still flagged "pending" (the
# CancelledError -> Task done-callback path doesn't synchronously
# clear the pending flag). Python emits "Task was destroyed but
# it is pending!" and starlette/anyio rolls back the SQLAlchemy
# session of whatever test happens to be running next.
#
# Manifestation: ``test_monthly_locked_bank_charge_overrides_user_value``
# (and friends) in test_bank_charges_pl.py fails 500 Internal Server
# Error on /api/v2/monthly PUT — the route handler blows up because
# its DB session was rolled back by a Task's __del__ deep in the
# stack.
#
# Fix: monkey-patch a2wsgi's ASGIResponder so every Task it spawns
# is ALSO appended to a process-global strong-ref list. The list
# never shrinks within a test process, so Python GC can never
# reclaim them mid-test. Memory cost is bounded by total request
# count over a single test run — small (a few KB per task).
# Compared to per-test loop draining this is O(1) overhead per
# request; no scheduling cost between tests.
import a2wsgi.asgi as _a2wsgi_asgi
_LEAKED_TASK_REFS: list = []
_orig_start_asgi_app = _a2wsgi_asgi.ASGIResponder.start_asgi_app


async def _start_asgi_app_pinning_task(self, environ):
    task = await _orig_start_asgi_app(self, environ)
    _LEAKED_TASK_REFS.append(task)
    return task


_a2wsgi_asgi.ASGIResponder.start_asgi_app = _start_asgi_app_pinning_task


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


def seed_test_data():
    from app import User, Store, _seed_tv_catalogs
    # TV-display catalogs (companies + banks) are seeded by init_db
    # in production but the test fixture drop_all/create_all cycle
    # resets every table — we rebuild them here so picker UI tests
    # see the same canonical 12 + 34 entries production does.
    _seed_tv_catalogs()
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
        from app import Store
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
        from app import User
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
    from app import Store
    with flask_app.app_context():
        return Store.query.filter_by(slug="test-store").first().id


@pytest.fixture
def test_admin_id():
    """The User.id of the seeded admin@test.com user."""
    from app import User
    with flask_app.app_context():
        return User.query.filter_by(username="admin@test.com").first().id


def make_employee_client(store_id, *, username_suffix="emp"):
    """Return a Flask test client authenticated as a new employee user
    at the given store. Each call creates a fresh User row so tests
    that need multiple employees can call this multiple times."""
    from app import User
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
    from app import Transfer
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
