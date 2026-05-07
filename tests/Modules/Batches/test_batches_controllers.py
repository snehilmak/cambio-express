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
    login = client.post(
        "/api/v2/auth/login",
        json={
            "username": "superadmin",
            "password": "super2025!",
            "store_id": None,
        },
    )
    token = login.get_json()["access_token"]
    resp = client.get(
        "/api/v2/batches",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403
