"""HTTP integration tests for ``/api/v2/dashboard/summary``
(superadmin payload).

The user reported the Platform Controls page showing "—" for
Active / Paid / Inactive / MRR. Root cause: the SPA reads
``active_stores`` / ``paid_stores`` / ``mrr_total`` / etc. but
``superadmin_dashboard_context`` returns ``active_count`` /
``paid_count`` / ``estimated_mrr``. ``_superadmin_summary`` now
adapts the legacy keys to the SPA-facing shape; this file pins
the contract so the next refactor doesn't regress.
"""
from tests._app import db, db_session


def _login_superadmin(client):
    from tests.conftest import login_superadmin
    return login_superadmin(client)


def test_summary_requires_jwt(client):
    resp = client.get("/api/v2/dashboard/summary")
    assert resp.status_code == 401


def test_summary_returns_superadmin_shape(client):
    """Superadmin payload carries ``role="superadmin"`` plus the
    KPI scalars the Platform Controls page reads."""
    token = _login_superadmin(client)
    resp = client.get(
        "/api/v2/dashboard/summary",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["role"] == "superadmin"


def test_summary_exposes_spa_facing_store_counts(client):
    """The KPI tiles read ``active_stores`` etc. — without the
    adapter they'd render as "—" forever even with stores in DB."""
    token = _login_superadmin(client)
    body = client.get(
        "/api/v2/dashboard/summary",
        headers={"Authorization": f"Bearer {token}"},
    ).get_json()
    for key in (
        "active_stores", "trial_stores", "paid_stores",
        "inactive_stores", "total_stores",
    ):
        assert key in body, (
            f"Missing {key!r} on superadmin /dashboard/summary "
            f"response. SPA's Platform Controls reads it and "
            f"renders '—' without it. body keys = {list(body)}"
        )
        assert isinstance(body[key], int), body[key]


def test_summary_counts_a_seeded_active_store(client):
    """End-to-end: seed an extra active store and confirm
    ``active_stores`` increments. Validates that the adapter
    actually surfaces the live count instead of a stale snapshot."""
    from api.Modules.Tenancy.Models import Store
    token = _login_superadmin(client)
    baseline = client.get(
        "/api/v2/dashboard/summary",
        headers={"Authorization": f"Bearer {token}"},
    ).get_json()
    with db_session():
        db.session.add(Store(
            name="Active Pro Test", slug="active-pro-test",
            email="apt@example.com", plan="pro",
            is_active=True,
        ))
        db.session.commit()
    after = client.get(
        "/api/v2/dashboard/summary",
        headers={"Authorization": f"Bearer {token}"},
    ).get_json()
    assert after["active_stores"] == baseline["active_stores"] + 1


def test_summary_exposes_spa_facing_money_keys(client):
    """``mrr_total`` and ``arr_total`` back the MRR + ARR KPI tiles."""
    token = _login_superadmin(client)
    body = client.get(
        "/api/v2/dashboard/summary",
        headers={"Authorization": f"Bearer {token}"},
    ).get_json()
    assert "mrr_total" in body
    assert "arr_total" in body
    # ARR is MRR × 12 (annualised). Allow a tiny float epsilon.
    if isinstance(body["mrr_total"], (int, float)):
        assert abs(body["arr_total"] - body["mrr_total"] * 12) < 0.01


def test_summary_exposes_retention_queue_and_cancellations(client):
    """``retention_queue`` (stores past cancellation, still inside
    the 180-day window) and ``cancellations_30d`` round out the
    Platform Controls overview."""
    token = _login_superadmin(client)
    body = client.get(
        "/api/v2/dashboard/summary",
        headers={"Authorization": f"Bearer {token}"},
    ).get_json()
    assert "retention_queue" in body
    assert isinstance(body["retention_queue"], int)
    assert "cancellations_30d" in body


def test_summary_retention_queue_counts_pending_purge(client):
    """A store whose ``data_retention_until`` is in the future
    contributes to ``retention_queue``."""
    from datetime import datetime, timedelta
    from api.Modules.Tenancy.Models import Store
    token = _login_superadmin(client)
    baseline = client.get(
        "/api/v2/dashboard/summary",
        headers={"Authorization": f"Bearer {token}"},
    ).get_json()
    with db_session():
        db.session.add(Store(
            name="Retention Pending", slug="retention-pending",
            email="rp@example.com", plan="inactive",
            data_retention_until=datetime.utcnow() + timedelta(days=90),
        ))
        db.session.commit()
    after = client.get(
        "/api/v2/dashboard/summary",
        headers={"Authorization": f"Bearer {token}"},
    ).get_json()
    assert after["retention_queue"] == baseline["retention_queue"] + 1
