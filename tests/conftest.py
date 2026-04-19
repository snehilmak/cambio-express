import os
# Set test database BEFORE importing app so SQLAlchemy uses it
os.environ["DATABASE_URL"] = "sqlite:///test_cambio.db"
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-ci")
os.environ.setdefault("STRIPE_SECRET_KEY", "sk_test_fake_key")
os.environ.setdefault("STRIPE_BASIC_PRICE_ID", "price_basic_test")
os.environ.setdefault("STRIPE_PRO_PRICE_ID", "price_pro_test")
os.environ.setdefault("STRIPE_WEBHOOK_SECRET", "whsec_test_secret")

import pytest
from datetime import datetime, timedelta
from app import app as flask_app, db


def seed_test_data():
    from app import User, Store
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
    flask_app.config["TESTING"] = True
    return flask_app.test_client()


@pytest.fixture
def logged_in_client():
    """Client pre-authenticated as the test store admin."""
    flask_app.config["TESTING"] = True
    c = flask_app.test_client()
    with flask_app.app_context():
        from app import User
        u = User.query.filter_by(username="admin@test.com").first()
        uid, sid = u.id, u.store_id
    with c.session_transaction() as sess:
        sess["user_id"] = uid
        sess["role"] = "admin"
        sess["store_id"] = sid
    return c
