"""HTTP integration tests for the Monthly Controllers."""
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
    return resp.get_json()["access_token"]


def _seed_monthly(store_id, *, year=2026, month=1, **fields):
    from app import MonthlyFinancial, db
    row = MonthlyFinancial(
        store_id=store_id, year=year, month=month, **fields,
    )
    db.session.add(row); db.session.commit()
    return row.id


def test_monthly_returns_404_when_missing(client, test_store_id):
    token = _login(client, test_store_id)
    resp = client.get(
        "/api/v2/monthly/2026/3",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404


def test_monthly_returns_row_with_totals(client, test_store_id):
    """taxable_sales=100 + non_taxable=50 = 150 income;
    cash_expenses=20 + cash_payroll=30 = 50 expenses;
    net = 100."""
    from app import app as flask_app
    with flask_app.app_context():
        _seed_monthly(
            test_store_id, year=2026, month=2,
            taxable_sales=100.0, non_taxable=50.0,
            cash_expenses=20.0, cash_payroll=30.0,
        )
    token = _login(client, test_store_id)
    resp = client.get(
        "/api/v2/monthly/2026/2",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    body = resp.get_json()["report"]
    assert body["taxable_sales"] == 100.0
    assert body["total_income"]   == 150.0
    assert body["total_expenses"] == 50.0
    assert body["net_profit"]     == 100.0


def test_months_lists_logged(client, test_store_id):
    from app import app as flask_app
    with flask_app.app_context():
        _seed_monthly(test_store_id, year=2026, month=1, taxable_sales=10)
        _seed_monthly(test_store_id, year=2026, month=3, taxable_sales=20)
    token = _login(client, test_store_id)
    resp = client.get(
        "/api/v2/monthly/months",
        headers={"Authorization": f"Bearer {token}"},
    )
    body = resp.get_json()
    pairs = [(m["year"], m["month"]) for m in body["months"]]
    # Newest first.
    assert pairs[:2] == [(2026, 3), (2026, 1)]


def test_monthly_rejects_bad_month(client, test_store_id):
    token = _login(client, test_store_id)
    resp = client.get(
        "/api/v2/monthly/2026/13",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422


def test_monthly_requires_jwt():
    resp = _client().get("/monthly/2026/1")
    assert resp.status_code == 401


def test_monthly_rejects_superadmin(client):
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
        "/api/v2/monthly/2026/1",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403
