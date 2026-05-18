"""HTTP integration tests for the peak-hours heatmap endpoint.

  GET /api/v2/dashboard/peak-hours?days=N

Buckets transfers by (weekday, hour-of-day) in the store's
local timezone over the trailing ``days`` window. Feeds the
dashboard heatmap card.
"""
from datetime import datetime, timedelta

from tests._app import db, db_session


# ── Helpers ─────────────────────────────────────────────────


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
    from api.Modules.Tenancy.Models import StoreEmployee
    e = StoreEmployee(store_id=store_id, name="Peak Cashier", is_active=True)
    db.session.add(e); db.session.commit()
    return e.id


def _seed_transfer(store_id, emp_id, *, created_at: datetime,
                   status: str = "Sent"):
    from api.Modules.Transfers.Models import Transfer
    t = Transfer(
        store_id=store_id,
        send_date=created_at.date(),
        company="Intermex",
        service_type="Money Transfer",
        sender_name="Peak Sender",
        send_amount=100.0, fee=5.0, federal_tax=1.0,
        country="Mexico", recipient_name="Peak Recipient",
        sender_phone="5550000000", sender_phone_country="+1",
        sender_address="x", confirm_number="P-1",
        status=status, employee_id=emp_id,
        created_at=created_at,
    )
    db.session.add(t); db.session.commit()
    return t.id


def _set_store_tz(store_id, tz_name):
    from api.Modules.Tenancy.Models import Store
    s = db.session.get(Store, store_id)
    s.timezone = tz_name
    db.session.commit()


# ── Auth gating ─────────────────────────────────────────────


def test_peak_hours_requires_jwt(client):
    resp = client.get("/api/v2/dashboard/peak-hours")
    assert resp.status_code == 401


def test_peak_hours_requires_store_scope(client):
    """A superadmin login carries no store_id → 400 (owners /
    superadmin aggregate across umbrellas via /owner/* instead)."""
    from tests.conftest import login_superadmin
    token = login_superadmin(client)
    resp = client.get(
        "/api/v2/dashboard/peak-hours",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 400


def test_peak_hours_rejects_huge_days(client, test_store_id):
    token = _login_admin(client, test_store_id)
    resp = client.get(
        "/api/v2/dashboard/peak-hours?days=400",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422


def test_peak_hours_rejects_zero_days(client, test_store_id):
    token = _login_admin(client, test_store_id)
    resp = client.get(
        "/api/v2/dashboard/peak-hours?days=0",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422


# ── Empty state ─────────────────────────────────────────────


def test_peak_hours_empty_grid_when_no_transfers(
    client, test_store_id,
):
    """A store with no transfers comes back with a 7×24 grid
    of zeros + null busiest cell."""
    token = _login_admin(client, test_store_id)
    body = client.get(
        "/api/v2/dashboard/peak-hours?days=7",
        headers={"Authorization": f"Bearer {token}"},
    ).get_json()
    assert body["total_transfers"] == 0
    assert body["max_count"] == 0
    assert body["busiest"]["day_of_week"] is None
    assert body["busiest"]["hour"] is None
    assert len(body["grid"]) == 7
    assert all(len(row) == 24 for row in body["grid"])
    assert all(cell == 0 for row in body["grid"] for cell in row)


# ── Bucketing ───────────────────────────────────────────────


def test_peak_hours_buckets_in_utc_when_timezone_unset(
    client, test_store_id,
):
    """A store with no ``timezone`` column treats every
    ``created_at`` as UTC — no conversion."""
    # Anchor in the past so the < now filter doesn't drop the
    # row. 2025-05-19 (Monday) 14:30 UTC.
    moment = datetime(2025, 5, 19, 14, 30)
    with db_session():
        emp = _seed_employee(test_store_id)
        _seed_transfer(test_store_id, emp, created_at=moment)
    token = _login_admin(client, test_store_id)
    body = client.get(
        "/api/v2/dashboard/peak-hours?days=365",
        headers={"Authorization": f"Bearer {token}"},
    ).get_json()
    # Monday = 0, 14:30 → hour bucket 14.
    assert body["grid"][0][14] == 1
    assert body["total_transfers"] == 1
    assert body["busiest"]["day_of_week"] == 0
    assert body["busiest"]["hour"] == 14


def test_peak_hours_buckets_in_store_local_time(
    client, test_store_id,
):
    """A New York store sees 14:30 UTC as 10:30 EDT (UTC-4
    in May) → bucket 10. Validates the timezone-aware
    conversion."""
    moment = datetime(2025, 5, 19, 14, 30)  # Mon 14:30 UTC (past)
    with db_session():
        _set_store_tz(test_store_id, "America/New_York")
        emp = _seed_employee(test_store_id)
        _seed_transfer(test_store_id, emp, created_at=moment)
    token = _login_admin(client, test_store_id)
    body = client.get(
        "/api/v2/dashboard/peak-hours?days=365",
        headers={"Authorization": f"Bearer {token}"},
    ).get_json()
    assert body["grid"][0][10] == 1   # 10:30 EDT
    assert body["timezone"] == "America/New_York"
    assert body["busiest"]["hour"] == 10


def test_peak_hours_excludes_canceled_transfers(
    client, test_store_id,
):
    """Canceled / Rejected status doesn't count toward
    activity — the heatmap should show real workload only."""
    moment = datetime(2025, 5, 19, 14, 30)
    with db_session():
        emp = _seed_employee(test_store_id)
        _seed_transfer(test_store_id, emp, created_at=moment, status="Sent")
        _seed_transfer(test_store_id, emp, created_at=moment, status="Canceled")
        _seed_transfer(test_store_id, emp, created_at=moment, status="Rejected")
    token = _login_admin(client, test_store_id)
    body = client.get(
        "/api/v2/dashboard/peak-hours?days=365",
        headers={"Authorization": f"Bearer {token}"},
    ).get_json()
    assert body["total_transfers"] == 1


def test_peak_hours_respects_window(client, test_store_id):
    """Transfers older than the trailing ``days`` window
    aren't included."""
    now = datetime.utcnow()
    recent = now - timedelta(days=2)
    ancient = now - timedelta(days=180)
    with db_session():
        emp = _seed_employee(test_store_id)
        _seed_transfer(test_store_id, emp, created_at=recent)
        _seed_transfer(test_store_id, emp, created_at=ancient)
    token = _login_admin(client, test_store_id)
    body = client.get(
        "/api/v2/dashboard/peak-hours?days=7",
        headers={"Authorization": f"Bearer {token}"},
    ).get_json()
    assert body["total_transfers"] == 1


def test_peak_hours_busiest_cell_picks_max(client, test_store_id):
    """Heatmap reports the busiest (weekday, hour) cell so
    the SPA can call it out in the headline."""
    # Past Monday + Tuesday so they fall inside the trailing
    # 365-day window regardless of when the test runs.
    monday_3pm  = datetime(2025, 5, 19, 15, 0)
    tuesday_9am = datetime(2025, 5, 20,  9, 0)
    with db_session():
        emp = _seed_employee(test_store_id)
        # 3 on Mon 15:00 UTC, 1 on Tue 09:00 UTC.
        _seed_transfer(test_store_id, emp, created_at=monday_3pm)
        _seed_transfer(test_store_id, emp, created_at=monday_3pm)
        _seed_transfer(test_store_id, emp, created_at=monday_3pm)
        _seed_transfer(test_store_id, emp, created_at=tuesday_9am)
    token = _login_admin(client, test_store_id)
    body = client.get(
        "/api/v2/dashboard/peak-hours?days=365",
        headers={"Authorization": f"Bearer {token}"},
    ).get_json()
    assert body["busiest"]["day_of_week"] == 0   # Monday
    assert body["busiest"]["hour"] == 15
    assert body["busiest"]["count"] == 3
    assert body["max_count"] == 3
