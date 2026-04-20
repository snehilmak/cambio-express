import pytest
from app import app as flask_app, db


def make_employee(client, store_id, username="cashier", password="emppass123!"):
    """Helper: create an employee for the given store_id."""
    with flask_app.app_context():
        from app import User
        e = User(store_id=store_id, username=username,
                 full_name="Test Cashier", role="employee")
        e.set_password(password)
        db.session.add(e)
        db.session.commit()
        return e.id


def get_store_id(slug="test-store"):
    with flask_app.app_context():
        from app import Store
        return Store.query.filter_by(slug=slug).first().id


# ── Task 1: /login/<slug> ─────────────────────────────────────

def test_employee_login_with_valid_credentials(client):
    sid = get_store_id()
    make_employee(client, sid)
    resp = client.post("/login/test-store", data={
        "username": "cashier",
        "password": "emppass123!"
    }, follow_redirects=False)
    assert resp.status_code == 302
    assert "dashboard" in resp.headers["Location"]


def test_employee_login_wrong_password(client):
    sid = get_store_id()
    make_employee(client, sid)
    resp = client.post("/login/test-store", data={
        "username": "cashier",
        "password": "wrongpassword"
    })
    assert resp.status_code == 200
    assert b"Invalid username or password" in resp.data


def test_employee_login_unknown_slug_returns_404(client):
    resp = client.get("/login/no-such-store")
    assert resp.status_code == 404


def test_employee_login_get_page_shows_store_context(client):
    resp = client.get("/login/test-store")
    assert resp.status_code == 200
    assert b"Test Store" in resp.data or b"test-store" in resp.data
