"""HTTP integration tests for the shift-scheduling endpoints.

  GET    /api/v2/admin/timeclock/shifts?from=&to=&store_employee_id=
  POST   /api/v2/admin/timeclock/shifts
  PATCH  /api/v2/admin/timeclock/shifts/{id}
  DELETE /api/v2/admin/timeclock/shifts/{id}

The shifts endpoint is admin-only; non-admin roles get a 403.
Tenancy: every endpoint reads ``store_id`` from the JWT, so a
cross-store shift id 404s.
"""
from datetime import date, time

from tests._app import db, db_session
from tests.conftest import login_admin, login_employee, login_superadmin


# ── Helpers ─────────────────────────────────────────────────


def _trial_store_id():
    """Return the seeded trial store's id."""
    from api.Modules.Tenancy.Models import Store
    return db.session.query(Store.id).filter_by(slug="test-store").scalar()


def _seed_employee(store_id, *, name="Maria"):
    from api.Modules.Tenancy.Models import StoreEmployee
    e = StoreEmployee(store_id=store_id, name=name, is_active=True)
    db.session.add(e); db.session.commit()
    return e.id


def _seed_other_store():
    from api.Modules.Tenancy.Models import Store
    s = Store(
        name="Other Shift Store", slug="other-shift",
        email="other-shift@x.com", plan="basic",
    )
    db.session.add(s); db.session.commit()
    return s.id


def _seed_employee_login(store_id):
    """Add a `cashier@test.com` user under the trial store and
    return a JWT for it — used to assert the 403 gate."""
    from api.Modules.Tenancy.Models import User
    u = User(
        store_id=store_id, username="cashier@test.com",
        full_name="Cashier C", role="employee",
    )
    u.set_password("testpass123!")
    db.session.add(u); db.session.commit()
    return login_employee(
        client=None,  # populated by the caller
        store_id=store_id,
        username="cashier@test.com",
        password="testpass123!",
    )


# ── Auth gating ─────────────────────────────────────────────


def test_shifts_list_requires_jwt(client):
    resp = client.get("/api/v2/admin/timeclock/shifts?from=2026-05-01&to=2026-05-15")
    assert resp.status_code == 401


def test_shifts_list_requires_admin_role(client):
    """Employees can punch but can't see the schedule."""
    with db_session():
        store_id = _trial_store_id()
        from api.Modules.Tenancy.Models import User
        u = User(
            store_id=store_id, username="cashier@test.com",
            full_name="Cashier C", role="employee",
        )
        u.set_password("testpass123!")
        db.session.add(u); db.session.commit()
    token = login_employee(
        client, store_id=store_id,
        username="cashier@test.com", password="testpass123!",
    )
    resp = client.get(
        "/api/v2/admin/timeclock/shifts?from=2026-05-01&to=2026-05-15",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403


def test_shifts_list_requires_store_scope(client):
    """Superadmin without a store_id on the JWT can't list shifts
    — same guard as the payroll history endpoint."""
    token = login_superadmin(client)
    resp = client.get(
        "/api/v2/admin/timeclock/shifts?from=2026-05-01&to=2026-05-15",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403


# ── CRUD happy paths ───────────────────────────────────────


def test_shift_create_and_list(client):
    with db_session():
        store_id = _trial_store_id()
        emp_id = _seed_employee(store_id, name="Maria")
    token = login_admin(client, store_id)
    headers = {"Authorization": f"Bearer {token}"}
    body = {
        "store_employee_id": emp_id,
        "shift_date":  "2026-05-18",
        "start_time":  "09:00",
        "end_time":    "17:00",
        "notes":       "Opening",
    }
    resp = client.post(
        "/api/v2/admin/timeclock/shifts",
        json=body, headers=headers,
    )
    assert resp.status_code == 201
    created = resp.get_json()
    assert created["employee_name"] == "Maria"
    assert created["shift_date"] == "2026-05-18"
    assert created["start_time"] == "09:00:00"
    assert created["end_time"]   == "17:00:00"
    assert created["notes"]      == "Opening"
    shift_id = created["id"]

    # Listing the same window returns the shift.
    listed = client.get(
        "/api/v2/admin/timeclock/shifts?from=2026-05-18&to=2026-05-19",
        headers=headers,
    ).get_json()
    assert len(listed["rows"]) == 1
    assert listed["rows"][0]["id"] == shift_id


def test_shift_update_partial(client):
    with db_session():
        store_id = _trial_store_id()
        emp_id = _seed_employee(store_id, name="Maria")
    token = login_admin(client, store_id)
    headers = {"Authorization": f"Bearer {token}"}
    shift_id = client.post(
        "/api/v2/admin/timeclock/shifts",
        json={
            "store_employee_id": emp_id,
            "shift_date":  "2026-05-18",
            "start_time":  "09:00",
            "end_time":    "17:00",
        },
        headers=headers,
    ).get_json()["id"]

    # Patch only the end_time — start_time stays.
    patched = client.patch(
        f"/api/v2/admin/timeclock/shifts/{shift_id}",
        json={"end_time": "18:30"},
        headers=headers,
    ).get_json()
    assert patched["start_time"] == "09:00:00"
    assert patched["end_time"]   == "18:30:00"


def test_shift_delete(client):
    with db_session():
        store_id = _trial_store_id()
        emp_id = _seed_employee(store_id, name="Maria")
    token = login_admin(client, store_id)
    headers = {"Authorization": f"Bearer {token}"}
    shift_id = client.post(
        "/api/v2/admin/timeclock/shifts",
        json={
            "store_employee_id": emp_id,
            "shift_date":  "2026-05-18",
            "start_time":  "09:00",
            "end_time":    "17:00",
        },
        headers=headers,
    ).get_json()["id"]

    resp = client.delete(
        f"/api/v2/admin/timeclock/shifts/{shift_id}",
        headers=headers,
    )
    assert resp.status_code == 204
    # 404 on second delete.
    resp = client.delete(
        f"/api/v2/admin/timeclock/shifts/{shift_id}",
        headers=headers,
    )
    assert resp.status_code == 404


# ── Validation ─────────────────────────────────────────────


def test_shift_create_rejects_backwards_times(client):
    with db_session():
        store_id = _trial_store_id()
        emp_id = _seed_employee(store_id, name="Maria")
    token = login_admin(client, store_id)
    resp = client.post(
        "/api/v2/admin/timeclock/shifts",
        json={
            "store_employee_id": emp_id,
            "shift_date":  "2026-05-18",
            "start_time":  "17:00",
            "end_time":    "09:00",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422
    assert "after" in resp.get_json()["detail"].lower()


def test_shift_create_rejects_employee_at_other_store(client):
    with db_session():
        store_id = _trial_store_id()
        other_id = _seed_other_store()
        other_emp = _seed_employee(other_id, name="Other Maria")
    token = login_admin(client, store_id)
    resp = client.post(
        "/api/v2/admin/timeclock/shifts",
        json={
            "store_employee_id": other_emp,
            "shift_date":  "2026-05-18",
            "start_time":  "09:00",
            "end_time":    "17:00",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422
    assert "team" in resp.get_json()["detail"].lower()


def test_shift_window_validation(client):
    """``to`` must be after ``from`` and the window <= 370 days."""
    with db_session():
        store_id = _trial_store_id()
    token = login_admin(client, store_id)
    headers = {"Authorization": f"Bearer {token}"}
    # Equal dates — reject.
    resp = client.get(
        "/api/v2/admin/timeclock/shifts?from=2026-05-01&to=2026-05-01",
        headers=headers,
    )
    assert resp.status_code == 422
    # Window too wide.
    resp = client.get(
        "/api/v2/admin/timeclock/shifts?from=2024-01-01&to=2026-05-01",
        headers=headers,
    )
    assert resp.status_code == 422


def test_shift_cross_store_404(client):
    """Another store's shift id 404s rather than 200 — tenancy
    guard on the PATCH + DELETE paths."""
    with db_session():
        store_id = _trial_store_id()
        emp_id = _seed_employee(store_id, name="Maria")
    token = login_admin(client, store_id)
    headers = {"Authorization": f"Bearer {token}"}
    shift_id = client.post(
        "/api/v2/admin/timeclock/shifts",
        json={
            "store_employee_id": emp_id,
            "shift_date":  "2026-05-18",
            "start_time":  "09:00",
            "end_time":    "17:00",
        },
        headers=headers,
    ).get_json()["id"]

    # Seed a second store + admin, attempt to PATCH the first store's shift.
    with db_session():
        from api.Modules.Tenancy.Models import Store, User
        s2 = Store(
            name="Other", slug="other-shift-2",
            email="other2@x.com", plan="basic",
        )
        db.session.add(s2); db.session.flush()
        a2 = User(
            store_id=s2.id, username="admin2@test.com",
            full_name="Other Admin", role="admin",
        )
        a2.set_password("testpass123!")
        db.session.add(a2); db.session.commit()
        s2_id = s2.id

    token2 = login_admin(client, s2_id)
    resp = client.patch(
        f"/api/v2/admin/timeclock/shifts/{shift_id}",
        json={"notes": "tampered"},
        headers={"Authorization": f"Bearer {token2}"},
    )
    assert resp.status_code == 404
