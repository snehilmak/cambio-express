"""HTTP integration tests for /api/v2/superadmin/anomalies.

Backed by `compute_platform_anomalies()` (existing Service). The
endpoint is read-only and superadmin-scoped.
"""
from datetime import date, timedelta
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


def _login_superadmin(client):
    """Wraps the SPA two-step login (password → TOTP exchange)
    using the seeded superadmin's pre-enrolled TOTP secret. See
    tests/conftest.py for the secret + helper definition."""
    from tests.conftest import login_superadmin
    return login_superadmin(client)


def test_anomalies_requires_jwt(client):
    resp = client.get("/api/v2/superadmin/anomalies")
    assert resp.status_code == 401


def test_anomalies_rejects_admin_role(client, test_store_id):
    token = _login_admin(client, test_store_id)
    resp = client.get(
        "/api/v2/superadmin/anomalies",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403


def test_anomalies_returns_envelope(client):
    """Empty platform → empty rows envelope."""
    token = _login_superadmin(client)
    resp = client.get(
        "/api/v2/superadmin/anomalies",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert set(body.keys()) == {"rows", "total"}
    assert isinstance(body["rows"], list)
    assert body["total"] >= 0


def test_anomalies_surfaces_big_over_short(client, test_store_id):
    """A daily report with absolute over/short above the medium
    threshold should appear in the anomalies feed."""
    from api.Modules.DailyBook.Models import DailyReport
    from tests._app import db
    from api.Modules.Superadmin.Services.anomalies import (
        ANOMALY_OVERSHORT_MEDIUM_THRESHOLD,
    )
    today = date.today()
    with db_session():
        # Seed a daily report with a big over/short variance
        r = DailyReport(
            store_id=test_store_id,
            report_date=today - timedelta(days=1),
            over_short=ANOMALY_OVERSHORT_MEDIUM_THRESHOLD + 100.0,
        )
        db.session.add(r); db.session.commit()
    token = _login_superadmin(client)
    body = client.get(
        "/api/v2/superadmin/anomalies",
        headers={"Authorization": f"Bearer {token}"},
    ).get_json()
    big_overs = [a for a in body["rows"] if a["kind"] == "big_over_short"]
    assert len(big_overs) >= 1
    assert big_overs[0]["store_id"] == test_store_id
    assert big_overs[0]["severity"] in ("medium", "high")
