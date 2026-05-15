"""HTTP integration tests for the Monthly Controllers."""
from fastapi.testclient import TestClient
from tests._app import db, db_session
import pytest


@pytest.fixture
def api_client():
    from api.main import api_app
    with TestClient(api_app) as c:
        yield c


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
    from api.Modules.Monthly.Models import MonthlyFinancial
    from tests._app import db
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
    with db_session():
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
    with db_session():
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


def test_monthly_requires_jwt(api_client):
    resp = api_client.get("/monthly/2026/1")
    assert resp.status_code == 401


def test_monthly_rejects_superadmin(client):
    from tests.conftest import login_superadmin
    token = login_superadmin(client)
    resp = client.get(
        "/api/v2/monthly/2026/1",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403


# ── PUT /monthly/{year}/{month} ─────────────────────────────


def test_put_creates_when_missing(client, test_store_id):
    """First save for a (year, month) auto-creates the row."""
    token = _login(client, test_store_id)
    resp = client.put(
        "/api/v2/monthly/2026/4",
        json={
            "taxable_sales":      1000.0,
            "non_taxable":        500.0,
            "rebates_commissions": 50.0,
            "notes":              "april",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, resp.get_data(as_text=True)
    body = resp.get_json()["report"]
    assert body["taxable_sales"]      == 1000.0
    assert body["non_taxable"]        == 500.0
    assert body["rebates_commissions"] == 50.0
    assert body["notes"] == "april"


def test_put_updates_existing(client, test_store_id):
    with db_session():
        _seed_monthly(test_store_id, year=2026, month=5, taxable_sales=100)
    token = _login(client, test_store_id)
    resp = client.put(
        "/api/v2/monthly/2026/5",
        json={"taxable_sales": 999.0},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.get_json()["report"]["taxable_sales"] == 999.0


def test_put_rejects_extra_fields(client, test_store_id):
    """Schema is extra=forbid — auto-derived fields like
    cash_purchases must NOT be writable here."""
    token = _login(client, test_store_id)
    resp = client.put(
        "/api/v2/monthly/2026/6",
        json={
            "taxable_sales":  100.0,
            "cash_purchases": 500.0,  # auto-derived, not in schema
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422


def test_put_rejects_employee_role(client):
    """Cashier role cannot save monthly P&L."""
    from api.Modules.Tenancy.Models import User
    from tests._app import db
    with db_session():
        u = User(
            store_id=None, username="emp_monthly_test",
            role="employee", is_active=True,
        )
        u.set_password("emppass1234")
        db.session.add(u); db.session.commit()
    try:
        login = client.post(
            "/api/v2/auth/login",
            json={
                "username": "emp_monthly_test",
                "password": "emppass1234",
                "store_id": None,
            },
        )
        token = login.get_json()["access_token"]
        resp = client.put(
            "/api/v2/monthly/2026/7",
            json={"taxable_sales": 1.0},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 403
    finally:
        with db_session():
            u2 = db.session.query(User).filter_by(
                username="emp_monthly_test",
            ).first()
            if u2:
                db.session.delete(u2); db.session.commit()


def test_put_requires_jwt(client):
    resp = client.put(
        "/api/v2/monthly/2026/8",
        json={"taxable_sales": 1.0},
    )
    assert resp.status_code == 401


def test_put_rejects_bad_month(client, test_store_id):
    token = _login(client, test_store_id)
    resp = client.put(
        "/api/v2/monthly/2026/13",
        json={"taxable_sales": 1.0},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422


def test_put_rejects_superadmin(client):
    from tests.conftest import login_superadmin
    token = login_superadmin(client)
    resp = client.put(
        "/api/v2/monthly/2026/9",
        json={"taxable_sales": 1.0},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403
