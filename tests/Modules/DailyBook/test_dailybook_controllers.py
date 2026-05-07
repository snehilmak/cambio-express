"""HTTP integration tests for the DailyBook Controllers (PR 23)."""
from datetime import date, timedelta

from fastapi.testclient import TestClient


def _seed_report(store_id, report_date, **kwargs):
    from app import DailyReport, db
    r = DailyReport(
        store_id=store_id, report_date=report_date, **kwargs,
    )
    db.session.add(r); db.session.commit()
    return r.id


def _client():
    from api.main import api_app
    return TestClient(api_app)


# ── /daily/{store_id}/{report_date} ─────────────────────────


def test_get_report_returns_404_when_missing(test_store_id):
    today = date.today().isoformat()
    resp = _client().get(f"/daily/{test_store_id}/{today}")
    assert resp.status_code == 404


def test_get_report_returns_summary(test_store_id):
    from app import app as flask_app
    today = date.today()
    with flask_app.app_context():
        _seed_report(
            test_store_id, today,
            taxable_sales=100.0, sales_tax=10.0,
            cash_expense=20.0,
        )
    resp = _client().get(f"/daily/{test_store_id}/{today.isoformat()}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["report"]["taxable_sales"] == 100.0
    assert body["report"]["total_disbursements"] >= 20.0
    assert body["report"]["locked"] is False


def test_get_report_rejects_malformed_date(test_store_id):
    resp = _client().get(f"/daily/{test_store_id}/not-a-date")
    assert resp.status_code == 422


def test_get_report_rejects_zero_store_id():
    """Path validation: store_id must be ≥ 1."""
    resp = _client().get("/daily/0/2026-05-06")
    assert resp.status_code == 422


# ── /daily/{store_id}/period ────────────────────────────────


def test_period_returns_summary(test_store_id):
    from app import app as flask_app
    today = date.today()
    yesterday = today - timedelta(days=1)
    with flask_app.app_context():
        _seed_report(test_store_id, yesterday, taxable_sales=100.0)
        _seed_report(test_store_id, today, taxable_sales=200.0)
    resp = _client().get(
        f"/daily/{test_store_id}/period",
        params={"from": yesterday.isoformat(), "to": today.isoformat()},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["days_logged"] == 2
    assert body["total_receipts"] == 300.0


def test_period_swaps_when_from_after_to(test_store_id):
    """Mirror the Reports period dependency: if from > to, swap so the
    SQL window stays non-empty."""
    from app import app as flask_app
    today = date.today()
    yesterday = today - timedelta(days=1)
    with flask_app.app_context():
        _seed_report(test_store_id, today, taxable_sales=42.0)
    resp = _client().get(
        f"/daily/{test_store_id}/period",
        params={"from": today.isoformat(), "to": yesterday.isoformat()},
    )
    assert resp.status_code == 200
    assert resp.json()["total_receipts"] == 42.0


def test_period_requires_from_and_to(test_store_id):
    resp = _client().get(f"/daily/{test_store_id}/period")
    assert resp.status_code == 422


def test_period_rejects_malformed_dates(test_store_id):
    resp = _client().get(
        f"/daily/{test_store_id}/period",
        params={"from": "not-a-date", "to": "2026-05-06"},
    )
    assert resp.status_code == 422


def test_period_empty_range_returns_zeros(test_store_id):
    today = date.today().isoformat()
    resp = _client().get(
        f"/daily/{test_store_id}/period",
        params={"from": today, "to": today},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["days_logged"] == 0
    assert body["total_receipts"] == 0


# ── Strangler-fig dispatch ──────────────────────────────────


def test_flask_dispatcher_routes_daily_to_fastapi(client, test_store_id):
    from app import app as flask_app
    today = date.today()
    with flask_app.app_context():
        _seed_report(test_store_id, today, taxable_sales=99.0)
    resp = client.get(
        f"/api/v2/daily/{test_store_id}/{today.isoformat()}",
    )
    assert resp.status_code == 200
    assert resp.is_json
    assert resp.get_json()["report"]["taxable_sales"] == 99.0


def test_openapi_includes_daily_paths():
    resp = _client().get("/openapi.json")
    assert resp.status_code == 200
    paths = set(resp.json()["paths"].keys())
    assert "/daily/{store_id}/{report_date}" in paths
    assert "/daily/{store_id}/period" in paths


# ── PUT /daily/{store_id}/{report_date} (write-side) ────────


def _login_admin_token(client_, store_id):
    resp = client_.post(
        "/api/v2/auth/login",
        json={
            "username": "admin@test.com",
            "password": "testpass123!",
            "store_id": store_id,
        },
    )
    return resp.get_json()["access_token"]


def test_put_creates_report_when_missing(client, test_store_id):
    """First save for a day auto-creates the row + persists the
    submitted totals."""
    today_iso = date.today().isoformat()
    token = _login_admin_token(client, test_store_id)
    resp = client.put(
        f"/api/v2/daily/{test_store_id}/{today_iso}",
        json={
            "taxable_sales": 100.0,
            "non_taxable":   50.0,
            "sales_tax":     8.50,
            "notes":         "first save of the day",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, resp.get_data(as_text=True)
    body = resp.get_json()
    row = body["report"]
    assert row["taxable_sales"] == 100.0
    assert row["non_taxable"]   == 50.0
    assert row["sales_tax"]     == 8.50
    assert row["notes"]         == "first save of the day"


def test_put_updates_existing_report(client, test_store_id):
    from app import app as flask_app
    today = date.today()
    with flask_app.app_context():
        _seed_report(test_store_id, today, taxable_sales=10.0)
    token = _login_admin_token(client, test_store_id)
    resp = client.put(
        f"/api/v2/daily/{test_store_id}/{today.isoformat()}",
        json={"taxable_sales": 200.0},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.get_json()["report"]["taxable_sales"] == 200.0


def test_put_rejects_locked_report(client, test_store_id):
    from app import app as flask_app, DailyReport, db
    today = date.today()
    from datetime import datetime as _dt
    with flask_app.app_context():
        _seed_report(test_store_id, today, taxable_sales=5.0)
        r = (
            db.session.query(DailyReport)
              .filter_by(store_id=test_store_id, report_date=today)
              .first()
        )
        r.locked_at = _dt.utcnow()
        db.session.commit()

    token = _login_admin_token(client, test_store_id)
    resp = client.put(
        f"/api/v2/daily/{test_store_id}/{today.isoformat()}",
        json={"taxable_sales": 99.0},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403
    assert "lock" in resp.get_data(as_text=True).lower()


def test_put_rejects_cross_store_jwt(client, test_store_id):
    """Superadmin JWT (no store scope) cannot edit a store's
    daily book — same opaque 403 as a wrong-store JWT."""
    today = date.today().isoformat()
    login = client.post(
        "/api/v2/auth/login",
        json={
            "username": "superadmin", "password": "super2025!",
            "store_id": None,
        },
    )
    token = login.get_json()["access_token"]
    resp = client.put(
        f"/api/v2/daily/{test_store_id}/{today}",
        json={"taxable_sales": 99.0},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403


def test_put_rejects_extra_fields(client, test_store_id):
    """Schema is extra=forbid — attempting to write a
    line-item-derived field (money_transfer) must 422 rather
    than silently no-op."""
    today_iso = date.today().isoformat()
    token = _login_admin_token(client, test_store_id)
    resp = client.put(
        f"/api/v2/daily/{test_store_id}/{today_iso}",
        json={
            "taxable_sales": 100.0,
            "money_transfer": 999.0,  # derived; not in the schema
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422


def test_put_requires_jwt(test_store_id):
    today_iso = date.today().isoformat()
    resp = _client().put(
        f"/daily/{test_store_id}/{today_iso}",
        json={"taxable_sales": 100.0},
    )
    assert resp.status_code == 401
