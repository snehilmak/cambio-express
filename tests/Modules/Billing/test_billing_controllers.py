"""HTTP integration tests for the Billing Controllers.

Mounts at /api/v2/billing/*. Two endpoints:
  POST /billing/checkout  → mint Stripe Checkout URL
  POST /billing/portal    → mint Stripe Billing Portal URL

Stripe SDK calls are monkeypatched to avoid network egress.
"""
from unittest.mock import patch
from tests._app import db, db_session


def _login_admin(client, store_id):
    resp = client.post(
        "/api/v2/auth/login",
        json={
            "username": "admin@test.com",
            "password": "testpass123!",
            "store_id": store_id,
        },
    )
    return resp.get_json()["access_token"]


def _seed_employee(store_id):
    from api.Modules.Tenancy.Models import User
    from tests._app import db
    e = User(
        store_id=store_id, username="emp@test.com",
        full_name="Emp", role="employee",
    )
    e.set_password("emppass1!")
    db.session.add(e); db.session.commit()


def _login_employee(client, store_id):
    with db_session():
        from api.Modules.Tenancy.Models import User
        if not db.session.query(User).filter_by(username="emp@test.com").first():
            _seed_employee(store_id)
    resp = client.post(
        "/api/v2/auth/login",
        json={
            "username": "emp@test.com",
            "password": "emppass1!",
            "store_id": store_id,
        },
    )
    return resp.get_json()["access_token"]


def _set_store_customer_id(store_id, customer_id):
    """Stripe doesn't mint a customer until the first checkout. The
    /billing/portal endpoint requires one to exist — this helper
    bypasses the real Stripe call by writing the ID directly."""
    from api.Modules.Tenancy.Models import Store
    from tests._app import db
    with db_session():
        s = db.session.query(Store).filter_by(id=store_id).first()
        s.stripe_customer_id = customer_id
        db.session.commit()


# ── Auth gating ─────────────────────────────────────────────


def test_checkout_requires_jwt(client):
    resp = client.post("/api/v2/billing/checkout", json={"plan": "basic"})
    assert resp.status_code == 401


def test_checkout_rejects_employee_role(client, test_store_id):
    token = _login_employee(client, test_store_id)
    resp = client.post(
        "/api/v2/billing/checkout",
        json={"plan": "basic"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403


def test_portal_requires_jwt(client):
    resp = client.post("/api/v2/billing/portal")
    assert resp.status_code == 401


def test_portal_rejects_employee_role(client, test_store_id):
    token = _login_employee(client, test_store_id)
    resp = client.post(
        "/api/v2/billing/portal",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403


# ── Schema validation ───────────────────────────────────────


def test_checkout_rejects_missing_plan(client, test_store_id):
    token = _login_admin(client, test_store_id)
    resp = client.post(
        "/api/v2/billing/checkout",
        json={},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422


def test_checkout_rejects_extra_fields(client, test_store_id):
    """Pydantic schema is `extra="forbid"` — typos must 422."""
    token = _login_admin(client, test_store_id)
    resp = client.post(
        "/api/v2/billing/checkout",
        json={"plan": "basic", "promo_code": "xyz"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422


# ── Checkout happy path ─────────────────────────────────────


def test_checkout_returns_url_for_valid_plan(client, test_store_id):
    token = _login_admin(client, test_store_id)
    fake_url = "https://checkout.stripe.com/c/pay/cs_test_abc"
    with patch(
        "api.Modules.Billing.Services.create_checkout_session",
        return_value=fake_url,
    ):
        resp = client.post(
            "/api/v2/billing/checkout",
            json={"plan": "basic"},
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body == {"url": fake_url}


def test_checkout_invalid_plan_returns_422(client, test_store_id):
    from api.Modules.Billing.Services import InvalidPlanError
    token = _login_admin(client, test_store_id)
    with patch(
        "api.Modules.Billing.Services.create_checkout_session",
        side_effect=InvalidPlanError("nope"),
    ):
        resp = client.post(
            "/api/v2/billing/checkout",
            json={"plan": "platinum_unicorn"},
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 422


def test_checkout_stripe_error_returns_502(client, test_store_id):
    from api.Modules.Billing.Services import StripeServiceError
    token = _login_admin(client, test_store_id)
    with patch(
        "api.Modules.Billing.Services.create_checkout_session",
        side_effect=StripeServiceError("boom"),
    ):
        resp = client.post(
            "/api/v2/billing/checkout",
            json={"plan": "basic"},
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 502


# ── Portal happy path ───────────────────────────────────────


def test_portal_returns_url_when_customer_exists(client, test_store_id):
    _set_store_customer_id(test_store_id, "cus_test_abc")
    token = _login_admin(client, test_store_id)
    fake_url = "https://billing.stripe.com/p/session/test_abc"
    with patch(
        "api.Modules.Billing.Services.create_billing_portal_session",
        return_value=fake_url,
    ):
        resp = client.post(
            "/api/v2/billing/portal",
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 200
    assert resp.get_json() == {"url": fake_url}


def test_portal_409_when_no_customer_id(client, test_store_id):
    """Trial stores haven't been to Stripe yet — no customer ID
    means we can't open the portal. Surface 409 so the SPA can
    show 'subscribe first' instead of a generic error."""
    token = _login_admin(client, test_store_id)
    resp = client.post(
        "/api/v2/billing/portal",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 409


def test_portal_stripe_error_returns_502(client, test_store_id):
    from api.Modules.Billing.Services import StripeServiceError
    _set_store_customer_id(test_store_id, "cus_test_abc")
    token = _login_admin(client, test_store_id)
    with patch(
        "api.Modules.Billing.Services.create_billing_portal_session",
        side_effect=StripeServiceError("boom"),
    ):
        resp = client.post(
            "/api/v2/billing/portal",
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 502
