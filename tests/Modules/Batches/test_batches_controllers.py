"""HTTP integration tests for the Batches Controllers."""
from datetime import date

from fastapi.testclient import TestClient


def _client():
    from api.main import api_app
    return TestClient(api_app)


def _login(client_, store_id):
    resp = client_.post(
        "/api/v2/auth/login",
        json={
            "username": "admin@test.com",
            "password": "testpass123!",
            "store_id": store_id,
        },
    )
    assert resp.status_code == 200, resp.get_data(as_text=True)
    return resp.get_json()["access_token"]


def _seed_batch(store_id, *, ach_amount=1000.0, batch_ref="B-001",
                 company="Intermex", ach_date_=None, status="Pending"):
    from app import ACHBatch, db
    b = ACHBatch(
        store_id=store_id,
        ach_date=ach_date_ or date.today(),
        company=company,
        batch_ref=batch_ref,
        ach_amount=ach_amount,
        status=status,
    )
    db.session.add(b); db.session.commit()
    return b.id


def _seed_transfer(store_id, *, batch_ref, send_amount=500.0,
                    federal_tax=5.0, send_date_=None):
    from app import Transfer, db
    t = Transfer(
        store_id=store_id,
        send_date=send_date_ or date.today(),
        company="Intermex",
        sender_name="S",
        send_amount=send_amount,
        federal_tax=federal_tax,
        batch_id=batch_ref,
        status="Sent",
    )
    db.session.add(t); db.session.commit()
    return t.id


def test_list_returns_envelope(client, test_store_id):
    """Empty list when no batches; envelope shape pinned."""
    token = _login(client, test_store_id)
    resp = client.get(
        "/api/v2/batches",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert "rows" in body
    assert isinstance(body["rows"], list)


def test_list_returns_seeded_batches(client, test_store_id):
    from app import app as flask_app
    with flask_app.app_context():
        _seed_batch(test_store_id, ach_amount=2000.0, batch_ref="B-A1",
                    ach_date_=date(2026, 1, 5))
        _seed_batch(test_store_id, ach_amount=3500.0, batch_ref="B-A2",
                    ach_date_=date(2026, 1, 6))
    token = _login(client, test_store_id)
    resp = client.get(
        "/api/v2/batches",
        headers={"Authorization": f"Bearer {token}"},
    )
    body = resp.get_json()
    refs = [r["batch_ref"] for r in body["rows"]]
    assert "B-A1" in refs and "B-A2" in refs
    # Default sort: ach_date desc — B-A2 (1/6) comes first.
    assert refs.index("B-A2") < refs.index("B-A1")


def test_list_computes_variance_from_transfers(client, test_store_id):
    """Variance = ach_amount - Σ(send_amount + federal_tax)
    across linked transfers. Service should bulk-compute, not
    N+1."""
    from app import app as flask_app
    with flask_app.app_context():
        _seed_batch(
            test_store_id, ach_amount=1000.0, batch_ref="B-V",
            ach_date_=date(2026, 1, 7),
        )
        # 600 + 6 + 300 + 3 = 909, variance = 1000 - 909 = 91.0
        _seed_transfer(test_store_id, batch_ref="B-V",
                       send_amount=600.0, federal_tax=6.0)
        _seed_transfer(test_store_id, batch_ref="B-V",
                       send_amount=300.0, federal_tax=3.0)

    token = _login(client, test_store_id)
    resp = client.get(
        "/api/v2/batches",
        headers={"Authorization": f"Bearer {token}"},
    )
    rows = {r["batch_ref"]: r for r in resp.get_json()["rows"]}
    bv = rows["B-V"]
    assert bv["transfers_total"] == 909.0
    assert bv["variance"] == 91.0
    assert bv["transfer_count"] == 2


def test_list_supports_sort_by_ach_amount(client, test_store_id):
    from app import app as flask_app
    with flask_app.app_context():
        _seed_batch(test_store_id, ach_amount=100.0,
                    batch_ref="B-S1", ach_date_=date(2026, 2, 1))
        _seed_batch(test_store_id, ach_amount=999.0,
                    batch_ref="B-S2", ach_date_=date(2026, 2, 2))
    token = _login(client, test_store_id)
    resp = client.get(
        "/api/v2/batches?sort=ach_amount&direction=asc",
        headers={"Authorization": f"Bearer {token}"},
    )
    rows = resp.get_json()["rows"]
    refs = [r["batch_ref"] for r in rows if r["batch_ref"].startswith("B-S")]
    assert refs == ["B-S1", "B-S2"]


def test_list_rejects_bad_direction(client, test_store_id):
    token = _login(client, test_store_id)
    resp = client.get(
        "/api/v2/batches?direction=sideways",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422


def test_list_requires_jwt():
    resp = _client().get("/batches")
    assert resp.status_code == 401


def test_list_rejects_superadmin(client):
    """Superadmin (no store scope) can't list a specific
    store's batches."""
    from tests.conftest import login_superadmin
    token = login_superadmin(client)
    resp = client.get(
        "/api/v2/batches",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403


# ── GET /batches/{id} ───────────────────────────────────────


def test_get_batch_returns_envelope(client, test_store_id):
    from app import app as flask_app
    with flask_app.app_context():
        bid = _seed_batch(test_store_id, batch_ref="B-G1", ach_amount=500)
    token = _login(client, test_store_id)
    resp = client.get(
        f"/api/v2/batches/{bid}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["batch"]["batch_ref"] == "B-G1"


def test_get_batch_404_for_cross_tenant(client, test_store_id):  # noqa: ARG001
    token = _login(client, test_store_id)
    resp = client.get(
        "/api/v2/batches/99999",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404


# ── POST /batches ───────────────────────────────────────────


def test_create_batch_round_trip(client, test_store_id):
    token = _login(client, test_store_id)
    resp = client.post(
        "/api/v2/batches",
        json={
            "ach_date":   "2026-03-15",
            "company":    "Intermex",
            "batch_ref":  "B-NEW1",
            "ach_amount": 1500.0,
            "status":     "Pending",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201, resp.get_data(as_text=True)
    row = resp.get_json()["batch"]
    assert row["batch_ref"] == "B-NEW1"
    assert row["ach_amount"] == 1500.0
    assert row["transfers_total"] == 0.0  # no linked transfers
    assert row["transfer_count"] == 0


def test_create_batch_rejects_duplicate_ref(client, test_store_id):
    from app import app as flask_app
    with flask_app.app_context():
        _seed_batch(test_store_id, batch_ref="B-DUP")
    token = _login(client, test_store_id)
    resp = client.post(
        "/api/v2/batches",
        json={
            "ach_date":   "2026-03-15",
            "company":    "Intermex",
            "batch_ref":  "B-DUP",  # collision
            "ach_amount": 100.0,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422
    assert resp.get_json()["detail"]["field"] == "batch_ref"


def test_create_batch_rejects_bad_date(client, test_store_id):
    token = _login(client, test_store_id)
    resp = client.post(
        "/api/v2/batches",
        json={
            "ach_date":   "not-a-date",
            "company":    "Intermex",
            "batch_ref":  "B-BAD",
            "ach_amount": 100.0,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422


def test_create_batch_requires_admin_role(client):
    """Cashier role can't create batches."""
    from app import User, db, app as flask_app
    with flask_app.app_context():
        u = User(
            store_id=None, username="emp_batch_test",
            role="employee", is_active=True,
        )
        u.set_password("emppass1234")
        db.session.add(u); db.session.commit()
    try:
        login = client.post(
            "/api/v2/auth/login",
            json={
                "username": "emp_batch_test",
                "password": "emppass1234",
                "store_id": None,
            },
        )
        token = login.get_json()["access_token"]
        resp = client.post(
            "/api/v2/batches",
            json={
                "ach_date":   "2026-03-15",
                "company":    "Intermex",
                "batch_ref":  "B-EMP",
                "ach_amount": 100.0,
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 403
    finally:
        with flask_app.app_context():
            u2 = db.session.query(User).filter_by(
                username="emp_batch_test",
            ).first()
            if u2:
                db.session.delete(u2); db.session.commit()


# ── PUT /batches/{id} ───────────────────────────────────────


def test_update_batch_round_trip(client, test_store_id):
    from app import app as flask_app
    with flask_app.app_context():
        bid = _seed_batch(test_store_id, batch_ref="B-UPD", ach_amount=200)
    token = _login(client, test_store_id)
    resp = client.put(
        f"/api/v2/batches/{bid}",
        json={
            "ach_date":   "2026-04-01",
            "company":    "Maxi",
            "batch_ref":  "B-UPD-RENAMED",
            "ach_amount": 999.0,
            "status":     "Cleared",
            "reconciled": True,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    row = resp.get_json()["batch"]
    assert row["batch_ref"] == "B-UPD-RENAMED"
    assert row["company"] == "Maxi"
    assert row["ach_amount"] == 999.0
    assert row["reconciled"] is True


def test_update_batch_404_for_cross_tenant(client, test_store_id):  # noqa: ARG001
    token = _login(client, test_store_id)
    resp = client.put(
        "/api/v2/batches/9999",
        json={
            "ach_date":   "2026-04-01",
            "company":    "X",
            "batch_ref":  "B-X",
            "ach_amount": 1.0,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404


def test_update_batch_rejects_collision_with_other_ref(client, test_store_id):
    """Renaming batch B to share C's ref → 422."""
    from app import app as flask_app
    with flask_app.app_context():
        b1 = _seed_batch(test_store_id, batch_ref="B-1", ach_amount=10)
        _seed_batch(test_store_id, batch_ref="B-2", ach_amount=20)
    token = _login(client, test_store_id)
    resp = client.put(
        f"/api/v2/batches/{b1}",
        json={
            "ach_date":   "2026-04-01",
            "company":    "Intermex",
            "batch_ref":  "B-2",  # collision
            "ach_amount": 10.0,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422


# ── GET /batches/{id}/transfers ─────────────────────────────


def test_batch_transfers_round_trip(client, test_store_id):
    from app import app as flask_app
    with flask_app.app_context():
        _seed_batch(test_store_id, batch_ref="B-TXNS", ach_amount=600)
        _seed_transfer(test_store_id, batch_ref="B-TXNS",
                       send_amount=400.0, federal_tax=4.0)
        _seed_transfer(test_store_id, batch_ref="B-TXNS",
                       send_amount=200.0, federal_tax=2.0)
        bid = (
            __import__("app").ACHBatch.query
              .filter_by(store_id=test_store_id, batch_ref="B-TXNS")
              .first().id
        )
    token = _login(client, test_store_id)
    resp = client.get(
        f"/api/v2/batches/{bid}/transfers",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    transfers = resp.get_json()["transfers"]
    assert len(transfers) == 2


def test_batch_transfers_404_when_missing(client, test_store_id):
    token = _login(client, test_store_id)
    resp = client.get(
        "/api/v2/batches/99999/transfers",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404


def test_write_endpoints_require_jwt(client):
    """All three write paths reject unauthed callers."""
    g = client.get("/api/v2/batches/1")
    p = client.post("/api/v2/batches", json={
        "ach_date": "2026-01-01", "company": "X",
        "batch_ref": "X", "ach_amount": 1.0,
    })
    u = client.put("/api/v2/batches/1", json={
        "ach_date": "2026-01-01", "company": "X",
        "batch_ref": "X", "ach_amount": 1.0,
    })
    t = client.get("/api/v2/batches/1/transfers")
    assert g.status_code == 401
    assert p.status_code == 401
    assert u.status_code == 401
    assert t.status_code == 401
