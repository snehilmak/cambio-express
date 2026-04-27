import os
# Set test database BEFORE importing app so SQLAlchemy uses it
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-ci")
os.environ.setdefault("STRIPE_SECRET_KEY", "sk_test_fake_key")
os.environ.setdefault("STRIPE_BASIC_PRICE_ID", "price_basic_test")
os.environ.setdefault("STRIPE_PRO_PRICE_ID", "price_pro_test")
os.environ.setdefault("STRIPE_WEBHOOK_SECRET", "whsec_test_secret")

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


def seed_test_data():
    from app import User, Store, _seed_tv_catalogs
    # TV-display catalogs (companies + banks) are seeded by init_db
    # in production but the test fixture drop_all/create_all cycle
    # resets every table — we rebuild them here so picker UI tests
    # see the same canonical 12 + 34 entries production does.
    _seed_tv_catalogs()
    if not User.query.filter_by(username="superadmin", store_id=None).first():
        sa = User(username="superadmin", full_name="Platform Owner",
                  role="superadmin", store_id=None)
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
