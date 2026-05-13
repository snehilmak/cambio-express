"""HTTP integration tests for the ReturnChecks Controllers."""
from datetime import date


def _login(client, store_id):
    resp = client.post(
        "/api/v2/auth/login",
        json={
            "username": "admin@test.com",
            "password": "testpass123!",
            "store_id": store_id,
        },
    )
    return resp.get_json()["access_token"]


def _seed_rc(store_id, *, customer_name="Bouncer Co",
              amount=500.0, bounced_on_=None, status="pending"):
    from api.Modules.ReturnChecks.Models import ReturnCheck
    from app import db
    r = ReturnCheck(
        store_id=store_id,
        bounced_on=bounced_on_ or date.today(),
        customer_name=customer_name,
        check_number="123",
        payer_bank="Bank A",
        amount=amount,
        status=status,
    )
    db.session.add(r); db.session.commit()
    return r.id


# ── GET /return-checks ──────────────────────────────────────


def test_list_returns_envelope(client, test_store_id):
    token = _login(client, test_store_id)
    resp = client.get(
        "/api/v2/return-checks",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert "rows" in resp.get_json()


def test_list_filters_by_status(client, test_store_id):
    from app import app as flask_app
    with flask_app.app_context():
        _seed_rc(test_store_id, customer_name="Pending Co", status="pending")
        rc_loss = _seed_rc(test_store_id, customer_name="Loss Co", status="loss")
        _ = rc_loss
    token = _login(client, test_store_id)
    resp = client.get(
        "/api/v2/return-checks?status=pending",
        headers={"Authorization": f"Bearer {token}"},
    )
    rows = resp.get_json()["rows"]
    statuses = {r["status"] for r in rows}
    assert statuses == {"pending"}


# ── POST /return-checks ─────────────────────────────────────


def test_create_round_trip(client, test_store_id):
    token = _login(client, test_store_id)
    resp = client.post(
        "/api/v2/return-checks",
        json={
            "bounced_on":    "2026-04-15",
            "customer_name": "Acme Corp",
            "check_number":  "12345",
            "payer_bank":    "Wells Fargo",
            "amount":        750.0,
            "notes":         "second bounce",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201
    rc = resp.get_json()["return_check"]
    assert rc["customer_name"] == "Acme Corp"
    assert rc["amount"] == 750.0
    assert rc["status"] == "pending"


def test_create_rejects_zero_amount(client, test_store_id):
    token = _login(client, test_store_id)
    resp = client.post(
        "/api/v2/return-checks",
        json={
            "bounced_on":    "2026-04-15",
            "customer_name": "Bad Amount",
            "amount":        0.0,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422


def test_create_requires_admin_role(client):
    """Cashier role can't create return checks."""
    from api.Modules.Tenancy.Models import User
    from app import app as flask_app, db
    with flask_app.app_context():
        u = User(
            store_id=None, username="emp_rc_test",
            role="employee", is_active=True,
        )
        u.set_password("emppass1234")
        db.session.add(u); db.session.commit()
    try:
        login = client.post(
            "/api/v2/auth/login",
            json={
                "username": "emp_rc_test",
                "password": "emppass1234",
                "store_id": None,
            },
        )
        token = login.get_json()["access_token"]
        resp = client.post(
            "/api/v2/return-checks",
            json={
                "bounced_on":    "2026-04-15",
                "customer_name": "X",
                "amount":        100.0,
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 403
    finally:
        with flask_app.app_context():
            u2 = db.session.query(User).filter_by(
                username="emp_rc_test",
            ).first()
            if u2:
                db.session.delete(u2); db.session.commit()


# ── PUT /return-checks/{id} ─────────────────────────────────


def test_update_round_trip(client, test_store_id):
    from app import app as flask_app
    with flask_app.app_context():
        rid = _seed_rc(test_store_id, customer_name="Old Name")
    token = _login(client, test_store_id)
    resp = client.put(
        f"/api/v2/return-checks/{rid}",
        json={
            "bounced_on":    "2026-05-01",
            "customer_name": "New Name",
            "check_number":  "99",
            "payer_bank":    "Bank B",
            "amount":        300.0,
            "notes":         "renamed",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    rc = resp.get_json()["return_check"]
    assert rc["customer_name"] == "New Name"
    assert rc["amount"] == 300.0


# ── Status transitions ──────────────────────────────────────


def test_mark_loss_round_trip(client, test_store_id):
    from app import app as flask_app
    with flask_app.app_context():
        rid = _seed_rc(test_store_id, status="pending")
    token = _login(client, test_store_id)
    resp = client.post(
        f"/api/v2/return-checks/{rid}/mark-loss",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    rc = resp.get_json()["return_check"]
    assert rc["status"] == "loss"
    assert rc["status_changed_on"] != ""


def test_mark_fraud_rejects_non_pending(client, test_store_id):
    from app import app as flask_app
    with flask_app.app_context():
        rid = _seed_rc(test_store_id, status="loss")
    token = _login(client, test_store_id)
    resp = client.post(
        f"/api/v2/return-checks/{rid}/mark-fraud",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 409


def test_reopen_round_trip(client, test_store_id):
    from api.Modules.ReturnChecks.Models import ReturnCheck
    from app import app as flask_app, db
    with flask_app.app_context():
        rid = _seed_rc(test_store_id, status="loss")
        rc = db.session.get(ReturnCheck, rid)
        rc.status_changed_on = date.today()
        db.session.commit()
    token = _login(client, test_store_id)
    resp = client.post(
        f"/api/v2/return-checks/{rid}/reopen",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    rc = resp.get_json()["return_check"]
    assert rc["status"] == "pending"
    assert rc["status_changed_on"] == ""


def test_reopen_rejects_pending(client, test_store_id):
    from app import app as flask_app
    with flask_app.app_context():
        rid = _seed_rc(test_store_id, status="pending")
    token = _login(client, test_store_id)
    resp = client.post(
        f"/api/v2/return-checks/{rid}/reopen",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 409


# ── GET /return-checks/{id}/payments ────────────────────────


def test_payments_returns_envelope(client, test_store_id):
    from app import app as flask_app
    with flask_app.app_context():
        rid = _seed_rc(test_store_id)
    token = _login(client, test_store_id)
    resp = client.get(
        f"/api/v2/return-checks/{rid}/payments",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.get_json()["payments"] == []


def test_payments_404_when_missing(client, test_store_id):
    token = _login(client, test_store_id)
    resp = client.get(
        "/api/v2/return-checks/9999/payments",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404


# ── Auth ────────────────────────────────────────────────────


def test_endpoints_require_jwt(client):
    g = client.get("/api/v2/return-checks")
    p = client.post("/api/v2/return-checks", json={
        "bounced_on": "2026-01-01",
        "customer_name": "X",
        "amount": 1.0,
    })
    u = client.put("/api/v2/return-checks/1", json={
        "bounced_on": "2026-01-01",
        "customer_name": "X",
        "amount": 1.0,
    })
    ml = client.post("/api/v2/return-checks/1/mark-loss")
    mf = client.post("/api/v2/return-checks/1/mark-fraud")
    ro = client.post("/api/v2/return-checks/1/reopen")
    pa = client.get("/api/v2/return-checks/1/payments")
    for r in (g, p, u, ml, mf, ro, pa):
        assert r.status_code == 401


def test_list_rejects_superadmin(client):
    from tests.conftest import login_superadmin
    token = login_superadmin(client)
    resp = client.get(
        "/api/v2/return-checks",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403
