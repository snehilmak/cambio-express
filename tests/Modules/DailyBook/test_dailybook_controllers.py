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
