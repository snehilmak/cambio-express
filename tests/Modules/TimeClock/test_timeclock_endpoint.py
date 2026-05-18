"""HTTP integration tests for the TimeClock module.

  POST /api/v2/timeclock/clock-in
  POST /api/v2/timeclock/clock-out
  GET  /api/v2/timeclock/status
  GET  /api/v2/admin/timeclock?from=&to=&store_employee_id=
"""
from datetime import date, datetime, timedelta

from tests._app import db, db_session


# ── Helpers ─────────────────────────────────────────────────


def _login(client_, store_id, *, username="admin@test.com",
           password="testpass123!"):
    resp = client_.post(
        "/api/v2/auth/login",
        json={
            "username": username, "password": password,
            "store_id": store_id,
        },
    )
    return resp.get_json()["access_token"]


def _seed_employee(store_id, *, name="Maria"):
    from api.Modules.Tenancy.Models import StoreEmployee
    e = StoreEmployee(store_id=store_id, name=name, is_active=True)
    db.session.add(e); db.session.commit()
    return e.id


def _seed_inactive_employee(store_id, *, name="Inactive Ivan"):
    from api.Modules.Tenancy.Models import StoreEmployee
    e = StoreEmployee(store_id=store_id, name=name, is_active=False)
    db.session.add(e); db.session.commit()
    return e.id


def _seed_other_store():
    from api.Modules.Tenancy.Models import Store
    s = Store(
        name="Other Store", slug="other-tc",
        email="other-tc@x.com", plan="basic",
    )
    db.session.add(s); db.session.commit()
    return s.id


# ── Auth gating ─────────────────────────────────────────────


def test_clock_in_requires_jwt(client):
    resp = client.post(
        "/api/v2/timeclock/clock-in",
        json={"store_employee_id": 1, "notes": ""},
    )
    assert resp.status_code == 401


def test_clock_in_requires_store_scope(client):
    """Owner / superadmin without a store_id on the JWT can't
    punch in — there's no store to bind the entry to. Mirrors
    the existing ``resolve_store_scope`` guard."""
    from tests.conftest import login_superadmin
    token = login_superadmin(client)
    resp = client.post(
        "/api/v2/timeclock/clock-in",
        json={"store_employee_id": 1, "notes": ""},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403


# ── Clock in ────────────────────────────────────────────────


def test_clock_in_creates_open_entry(client, test_store_id):
    with db_session():
        emp_id = _seed_employee(test_store_id, name="Punch Maria")
    token = _login(client, test_store_id)
    resp = client.post(
        "/api/v2/timeclock/clock-in",
        json={"store_employee_id": emp_id, "notes": "shift start"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201, resp.get_data(as_text=True)
    row = resp.get_json()["entry"]
    assert row["store_employee_id"] == emp_id
    assert row["employee_name"] == "Punch Maria"
    assert row["clock_out_at"] is None
    assert row["hours_worked"] is None
    assert row["notes"] == "shift start"
    assert row["clock_in_at"]  # non-empty ISO string

    # Verify persistence.
    from api.Modules.TimeClock.Models import TimeClockEntry
    with db_session():
        entry = db.session.get(TimeClockEntry, row["id"])
        assert entry is not None
        assert entry.store_id == test_store_id
        assert entry.clock_out_at is None


def test_clock_in_twice_for_same_employee_409s(client, test_store_id):
    """The "is already clocked in" guard fires server-side so
    a double-tap on the SPA button (or two devices) can't
    open two overlapping shifts for one person."""
    with db_session():
        emp_id = _seed_employee(test_store_id, name="Double Tap")
    token = _login(client, test_store_id)
    first = client.post(
        "/api/v2/timeclock/clock-in",
        json={"store_employee_id": emp_id, "notes": ""},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert first.status_code == 201
    second = client.post(
        "/api/v2/timeclock/clock-in",
        json={"store_employee_id": emp_id, "notes": ""},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert second.status_code == 409
    assert "already clocked in" in second.get_data(as_text=True).lower()


def test_clock_in_404s_for_cross_tenant_employee(client, test_store_id):
    """Picking a roster row that belongs to another store
    returns 404 (same shape as a missing row) so the SPA
    can't enumerate cross-tenant ids."""
    with db_session():
        other_store_id = _seed_other_store()
        other_emp_id = _seed_employee(other_store_id, name="Foreign Emp")
    token = _login(client, test_store_id)
    resp = client.post(
        "/api/v2/timeclock/clock-in",
        json={"store_employee_id": other_emp_id, "notes": ""},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404


def test_clock_in_404s_for_inactive_employee(client, test_store_id):
    """Deactivated roster members can't punch — the admin
    needs to reactivate them in Settings → Team first."""
    with db_session():
        emp_id = _seed_inactive_employee(test_store_id)
    token = _login(client, test_store_id)
    resp = client.post(
        "/api/v2/timeclock/clock-in",
        json={"store_employee_id": emp_id, "notes": ""},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404
    assert "deactivated" in resp.get_data(as_text=True).lower()


# ── Clock out ───────────────────────────────────────────────


def test_clock_out_closes_open_entry_and_computes_hours(
    client, test_store_id,
):
    """End-to-end: clock in, manually backdate the entry's
    ``clock_in_at`` by 90 minutes, clock out, verify the
    response carries the closed row + a ``hours_worked``
    near 1.5."""
    from api.Modules.TimeClock.Models import TimeClockEntry
    with db_session():
        emp_id = _seed_employee(test_store_id, name="Hours Helper")
    token = _login(client, test_store_id)

    resp_in = client.post(
        "/api/v2/timeclock/clock-in",
        json={"store_employee_id": emp_id, "notes": ""},
        headers={"Authorization": f"Bearer {token}"},
    )
    entry_id = resp_in.get_json()["entry"]["id"]

    # Backdate clock_in so the elapsed delta is deterministic.
    with db_session():
        entry = db.session.get(TimeClockEntry, entry_id)
        entry.clock_in_at = datetime.utcnow() - timedelta(minutes=90)
        db.session.commit()

    resp_out = client.post(
        "/api/v2/timeclock/clock-out",
        json={"store_employee_id": emp_id, "notes": "wrap"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp_out.status_code == 200, resp_out.get_data(as_text=True)
    row = resp_out.get_json()["entry"]
    assert row["clock_out_at"] is not None
    assert row["hours_worked"] is not None
    # Allow some scheduler slack — the test could take a few hundred ms.
    assert 1.49 <= row["hours_worked"] <= 1.52
    assert "wrap" in row["notes"]


def test_clock_out_409s_when_not_clocked_in(client, test_store_id):
    with db_session():
        emp_id = _seed_employee(test_store_id, name="Never Punched")
    token = _login(client, test_store_id)
    resp = client.post(
        "/api/v2/timeclock/clock-out",
        json={"store_employee_id": emp_id, "notes": ""},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 409
    assert "not currently clocked in" in resp.get_data(as_text=True).lower()


def test_clock_out_404s_for_cross_tenant_employee(client, test_store_id):
    with db_session():
        other_store_id = _seed_other_store()
        other_emp_id = _seed_employee(other_store_id, name="Foreign 2")
    token = _login(client, test_store_id)
    resp = client.post(
        "/api/v2/timeclock/clock-out",
        json={"store_employee_id": other_emp_id, "notes": ""},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404


def test_clock_out_appends_notes_when_clock_in_had_some(
    client, test_store_id,
):
    """Notes from both endpoints accumulate so the operator
    can leave context at the start AND end of the shift."""
    with db_session():
        emp_id = _seed_employee(test_store_id, name="Notes Person")
    token = _login(client, test_store_id)
    client.post(
        "/api/v2/timeclock/clock-in",
        json={"store_employee_id": emp_id, "notes": "covering for Bob"},
        headers={"Authorization": f"Bearer {token}"},
    )
    resp_out = client.post(
        "/api/v2/timeclock/clock-out",
        json={"store_employee_id": emp_id, "notes": "long line at close"},
        headers={"Authorization": f"Bearer {token}"},
    )
    notes = resp_out.get_json()["entry"]["notes"]
    assert "covering for Bob" in notes
    assert "long line at close" in notes


# ── Status ──────────────────────────────────────────────────


def test_status_lists_currently_open_entries(client, test_store_id):
    with db_session():
        a_id = _seed_employee(test_store_id, name="Open A")
        b_id = _seed_employee(test_store_id, name="Open B")
        c_id = _seed_employee(test_store_id, name="Closed C")
    token = _login(client, test_store_id)
    # Open two; clock the third in and right out.
    client.post(
        "/api/v2/timeclock/clock-in",
        json={"store_employee_id": a_id, "notes": ""},
        headers={"Authorization": f"Bearer {token}"},
    )
    client.post(
        "/api/v2/timeclock/clock-in",
        json={"store_employee_id": b_id, "notes": ""},
        headers={"Authorization": f"Bearer {token}"},
    )
    client.post(
        "/api/v2/timeclock/clock-in",
        json={"store_employee_id": c_id, "notes": ""},
        headers={"Authorization": f"Bearer {token}"},
    )
    client.post(
        "/api/v2/timeclock/clock-out",
        json={"store_employee_id": c_id, "notes": ""},
        headers={"Authorization": f"Bearer {token}"},
    )

    resp = client.get(
        "/api/v2/timeclock/status",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    open_ids = {
        r["store_employee_id"] for r in resp.get_json()["open_entries"]
    }
    assert open_ids == {a_id, b_id}


def test_status_isolated_per_store(client, test_store_id):
    """An open shift at another store doesn't leak into this
    store's status panel."""
    with db_session():
        other_store_id = _seed_other_store()
        other_emp = _seed_employee(other_store_id, name="Other Open")
        # Directly seed an open entry on the other store to avoid
        # needing a JWT for that store.
        from api.Modules.TimeClock.Models import TimeClockEntry
        db.session.add(TimeClockEntry(
            store_id=other_store_id,
            store_employee_id=other_emp,
            clock_in_at=datetime.utcnow(),
        ))
        db.session.commit()
    token = _login(client, test_store_id)
    resp = client.get(
        "/api/v2/timeclock/status",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.get_json()["open_entries"] == []


# ── Admin payroll history ───────────────────────────────────


def test_admin_entries_requires_admin_role(client, test_store_id):
    """Cashiers (role=employee) can't view payroll history —
    only admin / owner / superadmin."""
    from api.Modules.Tenancy.Models import User
    with db_session():
        u = User(
            store_id=test_store_id, username="cashier_tc@x.com",
            role="employee", is_active=True,
        )
        u.set_password("emppass1234")
        db.session.add(u); db.session.commit()
    login = client.post(
        "/api/v2/auth/login",
        json={
            "username": "cashier_tc@x.com",
            "password": "emppass1234",
            "store_id": test_store_id,
        },
    )
    token = login.get_json()["access_token"]
    today = date.today().isoformat()
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    resp = client.get(
        f"/api/v2/admin/timeclock?from={today}&to={tomorrow}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403


def test_admin_entries_returns_window_with_totals(client, test_store_id):
    """Closed shifts inside the window sum into ``total_hours``;
    open entries (still in progress) appear in ``rows`` but
    are excluded from the total."""
    from api.Modules.TimeClock.Models import TimeClockEntry
    # Pick a "now" anchor far enough into a known date that
    # subtracting hours doesn't roll the seeded shifts off the
    # day boundary. UTC noon today is the safest anchor.
    today_dt = datetime.combine(date.today(), datetime.min.time())
    anchor   = today_dt + timedelta(hours=12)
    with db_session():
        emp = _seed_employee(test_store_id, name="Payroll Pat")
        # Closed shift: 2 hours (10:00 → 12:00)
        db.session.add(TimeClockEntry(
            store_id=test_store_id, store_employee_id=emp,
            clock_in_at=anchor - timedelta(hours=2),
            clock_out_at=anchor,
            hours_worked=2.0,
        ))
        # Closed shift: 4 hours (06:00 → 10:00)
        db.session.add(TimeClockEntry(
            store_id=test_store_id, store_employee_id=emp,
            clock_in_at=anchor - timedelta(hours=6),
            clock_out_at=anchor - timedelta(hours=2),
            hours_worked=4.0,
        ))
        # Open shift — inside the window, appears but doesn't
        # count toward the total.
        db.session.add(TimeClockEntry(
            store_id=test_store_id, store_employee_id=emp,
            clock_in_at=anchor - timedelta(minutes=30),
        ))
        db.session.commit()
    token = _login(client, test_store_id)
    today = date.today().isoformat()
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    resp = client.get(
        f"/api/v2/admin/timeclock?from={today}&to={tomorrow}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, resp.get_data(as_text=True)
    body = resp.get_json()
    assert len(body["rows"]) == 3
    assert body["total_hours"] == 6.0


def test_admin_entries_filters_by_employee(client, test_store_id):
    from api.Modules.TimeClock.Models import TimeClockEntry
    today_dt = datetime.combine(date.today(), datetime.min.time())
    anchor   = today_dt + timedelta(hours=12)
    with db_session():
        a = _seed_employee(test_store_id, name="A")
        b = _seed_employee(test_store_id, name="B")
        db.session.add(TimeClockEntry(
            store_id=test_store_id, store_employee_id=a,
            clock_in_at=anchor - timedelta(hours=2),
            clock_out_at=anchor - timedelta(hours=1),
            hours_worked=1.0,
        ))
        db.session.add(TimeClockEntry(
            store_id=test_store_id, store_employee_id=b,
            clock_in_at=anchor - timedelta(hours=3),
            clock_out_at=anchor - timedelta(hours=1),
            hours_worked=2.0,
        ))
        db.session.commit()
    token = _login(client, test_store_id)
    today = date.today().isoformat()
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    resp = client.get(
        f"/api/v2/admin/timeclock?from={today}&to={tomorrow}&store_employee_id={a}",
        headers={"Authorization": f"Bearer {token}"},
    )
    body = resp.get_json()
    assert len(body["rows"]) == 1
    assert body["rows"][0]["store_employee_id"] == a
    assert body["total_hours"] == 1.0


def test_admin_entries_rejects_inverted_window(client, test_store_id):
    token = _login(client, test_store_id)
    resp = client.get(
        "/api/v2/admin/timeclock?from=2026-05-15&to=2026-05-01",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422


def test_admin_entries_rejects_huge_window(client, test_store_id):
    token = _login(client, test_store_id)
    resp = client.get(
        "/api/v2/admin/timeclock?from=2020-01-01&to=2030-01-01",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422


def test_admin_entries_isolated_per_store(client, test_store_id):
    from api.Modules.TimeClock.Models import TimeClockEntry
    with db_session():
        other_store_id = _seed_other_store()
        other_emp = _seed_employee(other_store_id, name="Far Punch")
        db.session.add(TimeClockEntry(
            store_id=other_store_id, store_employee_id=other_emp,
            clock_in_at=datetime.utcnow() - timedelta(hours=1),
            clock_out_at=datetime.utcnow(),
            hours_worked=1.0,
        ))
        db.session.commit()
    token = _login(client, test_store_id)
    today = date.today().isoformat()
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    resp = client.get(
        f"/api/v2/admin/timeclock?from={today}&to={tomorrow}",
        headers={"Authorization": f"Bearer {token}"},
    )
    body = resp.get_json()
    assert body["rows"] == []
    assert body["total_hours"] == 0.0


# ── Audit ───────────────────────────────────────────────────


def test_clock_punch_writes_audit_log(client, test_store_id):
    """Both clock-in and clock-out write an OperatorAuditLog
    row keyed to target_type='time_clock_entry'."""
    from api.Modules.Audit.Models import OperatorAuditLog
    with db_session():
        emp_id = _seed_employee(test_store_id, name="Audit Anna")
    token = _login(client, test_store_id)
    client.post(
        "/api/v2/timeclock/clock-in",
        json={"store_employee_id": emp_id, "notes": ""},
        headers={"Authorization": f"Bearer {token}"},
    )
    client.post(
        "/api/v2/timeclock/clock-out",
        json={"store_employee_id": emp_id, "notes": ""},
        headers={"Authorization": f"Bearer {token}"},
    )
    with db_session():
        actions = sorted(
            r.action
            for r in db.session.query(OperatorAuditLog)
              .filter_by(
                  store_id=test_store_id, target_type="time_clock_entry",
              )
              .all()
        )
        assert actions == ["clock_in", "clock_out"]


# ── Admin CRUD ──────────────────────────────────────────────


def _employee_login(client, store_id):
    """Sign in as a non-admin employee — used to verify the
    admin gate. Reuses the test fixture's admin to create the
    employee row first."""
    from api.Modules.Tenancy.Models import User
    with db_session():
        u = User(
            store_id=store_id, username="cashier_tc_admin@x.com",
            role="employee", is_active=True,
        )
        u.set_password("emppass1234")
        db.session.add(u); db.session.commit()
    resp = client.post(
        "/api/v2/auth/login",
        json={
            "username": "cashier_tc_admin@x.com",
            "password": "emppass1234",
            "store_id": store_id,
        },
    )
    return resp.get_json()["access_token"]


def test_admin_create_backfills_entry(client, test_store_id):
    """Admin can create an entry from scratch — used when a
    cashier forgot to punch and the admin reconstructs the
    shift later."""
    with db_session():
        emp_id = _seed_employee(test_store_id, name="Backfill Bob")
    token = _login(client, test_store_id)
    resp = client.post(
        "/api/v2/admin/timeclock",
        json={
            "store_employee_id": emp_id,
            "clock_in_at":  "2026-05-15T09:00:00",
            "clock_out_at": "2026-05-15T17:00:00",
            "notes": "back-filled — forgot to punch",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201, resp.get_data(as_text=True)
    row = resp.get_json()["entry"]
    assert row["store_employee_id"] == emp_id
    assert row["hours_worked"] == 8.0
    assert row["notes"] == "back-filled — forgot to punch"


def test_admin_create_open_entry(client, test_store_id):
    """``clock_out_at`` omitted → entry stays open. Used when
    the admin needs to retroactively start a shift the cashier
    is still working."""
    with db_session():
        emp_id = _seed_employee(test_store_id, name="Open Olga")
    token = _login(client, test_store_id)
    resp = client.post(
        "/api/v2/admin/timeclock",
        json={
            "store_employee_id": emp_id,
            "clock_in_at": "2026-05-15T09:00:00",
            "notes": "",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201
    row = resp.get_json()["entry"]
    assert row["clock_out_at"] is None
    assert row["hours_worked"] is None


def test_admin_create_rejects_inverted_timestamps(client, test_store_id):
    with db_session():
        emp_id = _seed_employee(test_store_id, name="Backwards")
    token = _login(client, test_store_id)
    resp = client.post(
        "/api/v2/admin/timeclock",
        json={
            "store_employee_id": emp_id,
            "clock_in_at":  "2026-05-15T18:00:00",
            "clock_out_at": "2026-05-15T09:00:00",
            "notes": "",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422


def test_admin_create_rejects_employee_role(client, test_store_id):
    """Only admin / owner / superadmin can back-fill — cashiers
    can't bypass the normal clock-in flow."""
    with db_session():
        emp_id = _seed_employee(test_store_id, name="Gate Test")
    token = _employee_login(client, test_store_id)
    resp = client.post(
        "/api/v2/admin/timeclock",
        json={
            "store_employee_id": emp_id,
            "clock_in_at": "2026-05-15T09:00:00",
            "notes": "",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403


def test_admin_create_rejects_cross_tenant_employee(client, test_store_id):
    with db_session():
        other_store_id = _seed_other_store()
        other_emp = _seed_employee(other_store_id, name="Far Far Away")
    token = _login(client, test_store_id)
    resp = client.post(
        "/api/v2/admin/timeclock",
        json={
            "store_employee_id": other_emp,
            "clock_in_at": "2026-05-15T09:00:00",
            "notes": "",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404


def test_admin_update_recomputes_hours(client, test_store_id):
    """Edit the clock_out_at — server recomputes hours_worked
    from the new pair, and the audit row carries the diff."""
    from api.Modules.TimeClock.Models import TimeClockEntry
    from api.Modules.Audit.Models import OperatorAuditLog
    with db_session():
        emp_id = _seed_employee(test_store_id, name="Edit Eve")
        entry = TimeClockEntry(
            store_id=test_store_id, store_employee_id=emp_id,
            clock_in_at=datetime(2026, 5, 15, 9),
            clock_out_at=datetime(2026, 5, 15, 17),
            hours_worked=8.0,
        )
        db.session.add(entry); db.session.commit()
        entry_id = entry.id
    token = _login(client, test_store_id)
    resp = client.put(
        f"/api/v2/admin/timeclock/{entry_id}",
        json={"clock_out_at": "2026-05-15T18:00:00"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, resp.get_data(as_text=True)
    row = resp.get_json()["entry"]
    assert row["hours_worked"] == 9.0
    # Audit row carries the field-level diff.
    with db_session():
        audit = (
            db.session.query(OperatorAuditLog)
              .filter_by(
                  store_id=test_store_id,
                  target_type="time_clock_entry",
                  target_id=str(entry_id),
                  action="admin_update",
              )
              .one()
        )
        assert "clock_out_at" in audit.summary
        assert "hours_worked" in audit.summary
        assert "9.0" in audit.summary or "9" in audit.summary


def test_admin_update_can_reopen_closed_entry(client, test_store_id):
    """Setting ``clock_out_at: null`` re-opens a previously
    closed shift. Edge case for "ended the shift by mistake"."""
    from api.Modules.TimeClock.Models import TimeClockEntry
    with db_session():
        emp_id = _seed_employee(test_store_id, name="Reopen Rita")
        entry = TimeClockEntry(
            store_id=test_store_id, store_employee_id=emp_id,
            clock_in_at=datetime(2026, 5, 15, 9),
            clock_out_at=datetime(2026, 5, 15, 17),
            hours_worked=8.0,
        )
        db.session.add(entry); db.session.commit()
        entry_id = entry.id
    token = _login(client, test_store_id)
    resp = client.put(
        f"/api/v2/admin/timeclock/{entry_id}",
        json={"clock_out_at": None},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    row = resp.get_json()["entry"]
    assert row["clock_out_at"] is None
    assert row["hours_worked"] is None


def test_admin_update_partial_leaves_unrelated_fields(client, test_store_id):
    """Only the keys in the JSON body land on the row — omitted
    fields stay put. PUT-as-PATCH semantics."""
    from api.Modules.TimeClock.Models import TimeClockEntry
    with db_session():
        emp_id = _seed_employee(test_store_id, name="Patch Pat")
        entry = TimeClockEntry(
            store_id=test_store_id, store_employee_id=emp_id,
            clock_in_at=datetime(2026, 5, 15, 9),
            clock_out_at=datetime(2026, 5, 15, 17),
            hours_worked=8.0,
            notes="original",
        )
        db.session.add(entry); db.session.commit()
        entry_id = entry.id
    token = _login(client, test_store_id)
    resp = client.put(
        f"/api/v2/admin/timeclock/{entry_id}",
        json={"notes": "updated"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    row = resp.get_json()["entry"]
    assert row["notes"] == "updated"
    assert row["hours_worked"] == 8.0
    assert row["clock_out_at"] is not None


def test_admin_update_rejects_inverted_clock_pair(client, test_store_id):
    from api.Modules.TimeClock.Models import TimeClockEntry
    with db_session():
        emp_id = _seed_employee(test_store_id, name="Inverted")
        entry = TimeClockEntry(
            store_id=test_store_id, store_employee_id=emp_id,
            clock_in_at=datetime(2026, 5, 15, 9),
            clock_out_at=datetime(2026, 5, 15, 17),
            hours_worked=8.0,
        )
        db.session.add(entry); db.session.commit()
        entry_id = entry.id
    token = _login(client, test_store_id)
    resp = client.put(
        f"/api/v2/admin/timeclock/{entry_id}",
        json={"clock_in_at": "2026-05-15T20:00:00"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422


def test_admin_update_404s_for_cross_tenant_entry(client, test_store_id):
    """An entry belonging to another store returns 404 (same
    shape as a missing row) so the SPA can't enumerate
    cross-tenant ids."""
    from api.Modules.TimeClock.Models import TimeClockEntry
    with db_session():
        other_store_id = _seed_other_store()
        emp = _seed_employee(other_store_id, name="Foreign Entry")
        entry = TimeClockEntry(
            store_id=other_store_id, store_employee_id=emp,
            clock_in_at=datetime(2026, 5, 15, 9),
        )
        db.session.add(entry); db.session.commit()
        entry_id = entry.id
    token = _login(client, test_store_id)
    resp = client.put(
        f"/api/v2/admin/timeclock/{entry_id}",
        json={"notes": "drift"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404


def test_admin_delete_removes_entry_and_audits(client, test_store_id):
    from api.Modules.TimeClock.Models import TimeClockEntry
    from api.Modules.Audit.Models import OperatorAuditLog
    with db_session():
        emp_id = _seed_employee(test_store_id, name="Delete Dave")
        entry = TimeClockEntry(
            store_id=test_store_id, store_employee_id=emp_id,
            clock_in_at=datetime(2026, 5, 15, 9),
            clock_out_at=datetime(2026, 5, 15, 17),
            hours_worked=8.0,
        )
        db.session.add(entry); db.session.commit()
        entry_id = entry.id
    token = _login(client, test_store_id)
    resp = client.delete(
        f"/api/v2/admin/timeclock/{entry_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 204
    with db_session():
        assert db.session.get(TimeClockEntry, entry_id) is None
        # Audit row survives — that's the whole point of the
        # per-entry history view.
        audit = (
            db.session.query(OperatorAuditLog)
              .filter_by(
                  store_id=test_store_id,
                  target_type="time_clock_entry",
                  target_id=str(entry_id),
                  action="admin_delete",
              )
              .one()
        )
        assert "Delete Dave" in audit.summary


def test_admin_delete_rejects_employee_role(client, test_store_id):
    from api.Modules.TimeClock.Models import TimeClockEntry
    with db_session():
        emp_id = _seed_employee(test_store_id, name="Lock Down")
        entry = TimeClockEntry(
            store_id=test_store_id, store_employee_id=emp_id,
            clock_in_at=datetime(2026, 5, 15, 9),
        )
        db.session.add(entry); db.session.commit()
        entry_id = entry.id
    token = _employee_login(client, test_store_id)
    resp = client.delete(
        f"/api/v2/admin/timeclock/{entry_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403


def test_admin_history_returns_chain(client, test_store_id):
    """Per-entry history surfaces clock-in, admin edit, and
    every other audit row tied to that entry id, newest-first."""
    with db_session():
        emp_id = _seed_employee(test_store_id, name="History Helga")
    token = _login(client, test_store_id)
    # Clock-in via the normal endpoint to seed an audit row.
    resp_in = client.post(
        "/api/v2/timeclock/clock-in",
        json={"store_employee_id": emp_id, "notes": ""},
        headers={"Authorization": f"Bearer {token}"},
    )
    entry_id = resp_in.get_json()["entry"]["id"]
    # Admin edit to add a second row.
    client.put(
        f"/api/v2/admin/timeclock/{entry_id}",
        json={"notes": "fixed up after the fact"},
        headers={"Authorization": f"Bearer {token}"},
    )
    # History query.
    resp = client.get(
        f"/api/v2/admin/timeclock/{entry_id}/history",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, resp.get_data(as_text=True)
    rows = resp.get_json()["rows"]
    # Two rows: clock_in then admin_update. Newest-first.
    assert [r["action"] for r in rows] == ["admin_update", "clock_in"]
    # The admin_update row carries the field-level diff.
    assert "notes" in rows[0]["summary"]


def test_admin_history_404s_for_cross_tenant_entry(client, test_store_id):
    from api.Modules.TimeClock.Models import TimeClockEntry
    with db_session():
        other_store_id = _seed_other_store()
        emp = _seed_employee(other_store_id, name="Hist Foreign")
        entry = TimeClockEntry(
            store_id=other_store_id, store_employee_id=emp,
            clock_in_at=datetime(2026, 5, 15, 9),
        )
        db.session.add(entry); db.session.commit()
        entry_id = entry.id
    token = _login(client, test_store_id)
    resp = client.get(
        f"/api/v2/admin/timeclock/{entry_id}/history",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404


def test_admin_history_rejects_employee_role(client, test_store_id):
    from api.Modules.TimeClock.Models import TimeClockEntry
    with db_session():
        emp_id = _seed_employee(test_store_id, name="History Gate")
        entry = TimeClockEntry(
            store_id=test_store_id, store_employee_id=emp_id,
            clock_in_at=datetime(2026, 5, 15, 9),
        )
        db.session.add(entry); db.session.commit()
        entry_id = entry.id
    token = _employee_login(client, test_store_id)
    resp = client.get(
        f"/api/v2/admin/timeclock/{entry_id}/history",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403
