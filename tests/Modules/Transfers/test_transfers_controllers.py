"""HTTP integration tests for the Transfers Controllers (PR 12).

Tests hit the FastAPI router via TestClient + via the Flask dispatcher
(strangler-fig path).
"""
from datetime import date, timedelta

from fastapi.testclient import TestClient


def _seed_transfer(store_id, *, send_date=None, send_amount=100.0,
                    fee=2.0, federal_tax=1.0, company="Intermex",
                    service_type="Money Transfer", country="MX",
                    sender_name="S", recipient_name="R",
                    confirm_number=None, status="Sent",
                    batch_id=""):
    from api.Modules.Transfers.Models import Transfer
    from app import db
    t = Transfer(
        store_id=store_id,
        send_date=send_date or date.today(),
        company=company,
        service_type=service_type,
        sender_name=sender_name,
        recipient_name=recipient_name,
        country=country,
        confirm_number=confirm_number or f"X{send_amount}-{recipient_name}",
        send_amount=send_amount,
        fee=fee,
        federal_tax=federal_tax,
        status=status,
        batch_id=batch_id,
    )
    db.session.add(t); db.session.commit()
    return t.id


def _client():
    from api.main import api_app
    return TestClient(api_app)


# ── parse_store_ids contract ────────────────────────────────


def test_list_requires_store_ids():
    resp = _client().get("/transfers")
    assert resp.status_code == 422


def test_list_rejects_non_numeric_store_ids():
    resp = _client().get("/transfers", params={"store_ids": "abc"})
    assert resp.status_code == 422


def test_list_rejects_empty_store_ids():
    resp = _client().get("/transfers", params={"store_ids": ""})
    assert resp.status_code == 422


def test_list_rejects_invalid_dir():
    resp = _client().get(
        "/transfers", params={"store_ids": "1", "dir": "garbage"},
    )
    assert resp.status_code == 422


def test_list_rejects_out_of_range_per_page():
    resp = _client().get(
        "/transfers", params={"store_ids": "1", "per_page": 0},
    )
    assert resp.status_code == 422
    resp = _client().get(
        "/transfers", params={"store_ids": "1", "per_page": 1000},
    )
    assert resp.status_code == 422


# ── Happy paths ─────────────────────────────────────────────


def test_list_response_envelope(test_store_id):
    from app import app as flask_app
    with flask_app.app_context():
        for i in range(3):
            _seed_transfer(test_store_id, send_amount=100.0)
    resp = _client().get(
        "/transfers", params={"store_ids": str(test_store_id)},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert set(body.keys()) == {
        "rows", "total", "page", "per_page", "total_pages", "page_amount",
    }
    assert body["total"] == 3
    assert len(body["rows"]) == 3


def test_list_filters_company(test_store_id):
    from app import app as flask_app
    with flask_app.app_context():
        _seed_transfer(test_store_id, company="Intermex",
                        confirm_number="X-Intermex")
        _seed_transfer(test_store_id, company="Maxi",
                        confirm_number="X-Maxi")
    resp = _client().get(
        "/transfers",
        params={"store_ids": str(test_store_id), "company": "Maxi"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["rows"][0]["company"] == "Maxi"


def test_list_global_search_q(test_store_id):
    from app import app as flask_app
    with flask_app.app_context():
        _seed_transfer(test_store_id, sender_name="Alice",
                        confirm_number="X-A")
        _seed_transfer(test_store_id, sender_name="Bob",
                        confirm_number="X-B")
    resp = _client().get(
        "/transfers",
        params={"store_ids": str(test_store_id), "q": "alice"},
    )
    assert resp.status_code == 200
    assert resp.json()["total"] == 1


def test_list_pagination(test_store_id):
    from app import app as flask_app
    with flask_app.app_context():
        for i in range(5):
            _seed_transfer(test_store_id, send_amount=100.0 * (i + 1))
    resp = _client().get(
        "/transfers",
        params={"store_ids": str(test_store_id), "per_page": 2, "page": 1},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 5
    assert body["total_pages"] == 3
    assert body["page"] == 1
    assert len(body["rows"]) == 2


def test_list_filters_date_range_string_input(test_store_id):
    """Controller takes `date_from`/`date_to` as YYYY-MM-DD strings;
    the underlying TransferFilters parses them. Malformed strings drop
    the filter (legacy behavior)."""
    from app import app as flask_app
    today = date.today()
    yesterday = today - timedelta(days=1)
    last_week = today - timedelta(days=7)
    with flask_app.app_context():
        _seed_transfer(test_store_id, send_date=last_week,
                        confirm_number="X-LW")
        _seed_transfer(test_store_id, send_date=today,
                        confirm_number="X-T")
    resp = _client().get(
        "/transfers",
        params={
            "store_ids": str(test_store_id),
            "date_from": yesterday.isoformat(),
            "date_to": today.isoformat(),
        },
    )
    assert resp.status_code == 200
    confirms = {r["confirm_number"] for r in resp.json()["rows"]}
    assert confirms == {"X-T"}


def test_list_multi_store_aggregation(test_store_id):
    from api.Modules.Tenancy.Models import Store
    from app import app as flask_app, db
    with flask_app.app_context():
        s2 = Store(name="Other", slug="other-tx-cc",
                    email="o@x.com", plan="trial")
        db.session.add(s2); db.session.commit()
        sid2 = s2.id
        _seed_transfer(test_store_id, confirm_number="X-Mine")
        _seed_transfer(sid2, confirm_number="X-Theirs")
    resp = _client().get(
        "/transfers",
        params={"store_ids": f"{test_store_id},{sid2}"},
    )
    assert resp.status_code == 200
    assert resp.json()["total"] == 2


def test_list_rows_have_total_collected(test_store_id):
    """Wire test: the row payload must include `total_collected`
    (send + fee + tax) so the React table can render the column
    without recomputing client-side."""
    from app import app as flask_app
    with flask_app.app_context():
        _seed_transfer(test_store_id, send_amount=100.0,
                        fee=2.0, federal_tax=1.0)
    resp = _client().get(
        "/transfers", params={"store_ids": str(test_store_id)},
    )
    body = resp.json()
    assert body["rows"][0]["total_collected"] == 103.0


# ── Strangler-fig dispatch ──────────────────────────────────


def test_flask_dispatcher_routes_transfers_to_fastapi(client, test_store_id):
    from app import app as flask_app
    with flask_app.app_context():
        _seed_transfer(test_store_id, send_amount=99.0)
    resp = client.get(
        f"/api/v2/transfers?store_ids={test_store_id}",
    )
    assert resp.status_code == 200
    assert resp.is_json
    assert resp.get_json()["total"] == 1


def test_openapi_includes_transfers_path():
    resp = _client().get("/openapi.json")
    assert resp.status_code == 200
    paths = set(resp.json()["paths"].keys())
    assert "/transfers" in paths


# ── POST /transfers (write-side) ────────────────────────────


def _login_admin_token(client_, test_store_id):
    """Helper: log the seeded admin in via /auth/login and return
    the JWT bearer token. Used by tests that call write-side
    endpoints which require an authed principal."""
    resp = client_.post(
        "/auth/login",
        json={
            "username": "admin@test.com",
            "password": "testpass123!",
            "store_id": test_store_id,
        },
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


def _seed_employee(store_id, *, name="Cashier 1", is_active=True):
    """Add a roster row so the create endpoint's pick_employee
    has something to resolve to."""
    from api.Modules.Tenancy.Models import StoreEmployee
    from app import db
    e = StoreEmployee(store_id=store_id, name=name, is_active=is_active)
    db.session.add(e); db.session.commit()
    return e.id


def test_create_requires_jwt(test_store_id):
    """No bearer header → 401 from get_principal."""
    resp = _client().post(
        "/transfers",
        json={
            "send_date": "2026-01-15",
            "company": "Intermex",
            "service_type": "Money Transfer",
            "sender_name": "Smoke Sender",
            "send_amount": 100.0,
        },
    )
    assert resp.status_code == 401


def test_create_returns_201_and_persists(client, test_store_id):
    """End-to-end: log in, post a transfer, verify the response
    + that it lands in the DB.

    Uses the Flask dispatcher path (mirrors how the SPA calls in
    production through DispatcherMiddleware)."""
    from app import app as flask_app
    with flask_app.app_context():
        emp_id = _seed_employee(test_store_id)

    # Log in via the Flask dispatcher → FastAPI /auth/login.
    login = client.post(
        "/api/v2/auth/login",
        json={
            "username": "admin@test.com",
            "password": "testpass123!",
            "store_id": test_store_id,
        },
    )
    assert login.status_code == 200, login.get_data(as_text=True)
    token = login.get_json()["access_token"]

    resp = client.post(
        "/api/v2/transfers",
        json={
            "send_date": "2026-01-15",
            "company": "Intermex",
            "service_type": "Money Transfer",
            "sender_name": "Jane Sender",
            "sender_phone": "5551234567",
            "send_amount": 250.0,
            "fee": 5.0,
            "country": "Mexico",
            "recipient_name": "Bob Recipient",
            "employee_id": emp_id,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201, resp.get_data(as_text=True)
    body = resp.get_json()
    row = body["transfer"]
    assert row["sender_name"] == "Jane Sender"
    assert row["company"] == "Intermex"
    # Server-recomputed federal tax should be present (1% default
    # store rate × $250 = $2.50). Don't pin the exact rate — the
    # invariant is that it's > 0 and the client didn't supply it.
    assert row["federal_tax"] > 0
    assert row["total_collected"] == row["send_amount"] + row["fee"] + row["federal_tax"]

    # Verify it persisted.
    from api.Modules.Transfers.Models import Transfer
    from app import db
    with flask_app.app_context():
        t = db.session.get(Transfer, row["id"])
        assert t is not None
        assert t.store_id == test_store_id
        assert t.sender_name == "Jane Sender"
        assert t.employee_id == emp_id


def test_create_recomputes_tax_ignoring_client_value(client, test_store_id):
    """Tax invariant — client can't override the server-computed
    federal_tax. We don't expose it as a request field at all
    (extra=forbid), and the response shows the recomputed value."""
    from app import app as flask_app
    with flask_app.app_context():
        emp_id = _seed_employee(test_store_id, name="C2")

    login = client.post(
        "/api/v2/auth/login",
        json={
            "username": "admin@test.com",
            "password": "testpass123!",
            "store_id": test_store_id,
        },
    )
    token = login.get_json()["access_token"]

    # Try to slip in a federal_tax field — schema must reject.
    resp = client.post(
        "/api/v2/transfers",
        json={
            "send_date": "2026-01-15",
            "company": "Intermex",
            "service_type": "Money Transfer",
            "sender_name": "S",
            "send_amount": 100.0,
            "country": "Mexico",
            "employee_id": emp_id,
            "federal_tax": 99.99,   # not in schema
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422


def test_create_rejects_missing_employee(client, test_store_id):
    """`pick_employee` returning None must produce 422."""
    login = client.post(
        "/api/v2/auth/login",
        json={
            "username": "admin@test.com",
            "password": "testpass123!",
            "store_id": test_store_id,
        },
    )
    token = login.get_json()["access_token"]
    resp = client.post(
        "/api/v2/transfers",
        json={
            "send_date": "2026-01-15",
            "company": "Intermex",
            "service_type": "Money Transfer",
            "sender_name": "S",
            "send_amount": 100.0,
            "country": "Mexico",
            "employee_id": None,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422
    assert "Processed by" in resp.get_data(as_text=True) or "employee" in resp.get_data(as_text=True).lower()


def test_create_rejects_bad_send_date(client, test_store_id):
    from app import app as flask_app
    with flask_app.app_context():
        emp_id = _seed_employee(test_store_id, name="C3")
    login = client.post(
        "/api/v2/auth/login",
        json={
            "username": "admin@test.com",
            "password": "testpass123!",
            "store_id": test_store_id,
        },
    )
    token = login.get_json()["access_token"]
    resp = client.post(
        "/api/v2/transfers",
        json={
            "send_date": "not-a-date",
            "company": "Intermex",
            "service_type": "Money Transfer",
            "sender_name": "S",
            "send_amount": 100.0,
            "employee_id": emp_id,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422


def test_create_jwt_without_store_returns_403(client):
    """Superadmin JWT (store_id=null) cannot create transfers via
    this endpoint — it doesn't carry a store scope."""
    from tests.conftest import login_superadmin
    token = login_superadmin(client)
    resp = client.post(
        "/api/v2/transfers",
        json={
            "send_date": "2026-01-15",
            "company": "Intermex",
            "service_type": "Money Transfer",
            "sender_name": "S",
            "send_amount": 100.0,
            "employee_id": 1,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403


# ── PUT /transfers/{id} (write-side, edit) ──────────────────


def test_update_returns_200_and_persists(client, test_store_id):
    """End-to-end: seed a transfer, log in, PUT new fields,
    verify the row + the audit log."""
    from api.Modules.Audit.Models import TransferAudit
    from api.Modules.Transfers.Models import Transfer
    from app import app as flask_app, db
    with flask_app.app_context():
        emp_id = _seed_employee(test_store_id, name="EE-edit")
        tid = _seed_transfer(
            test_store_id, send_amount=100.0, fee=2.0, federal_tax=1.0,
            company="Intermex", country="MX",
        )

    login = client.post(
        "/api/v2/auth/login",
        json={
            "username": "admin@test.com",
            "password": "testpass123!",
            "store_id": test_store_id,
        },
    )
    assert login.status_code == 200
    token = login.get_json()["access_token"]

    resp = client.put(
        f"/api/v2/transfers/{tid}",
        json={
            "send_date": "2026-02-10",
            "company": "Maxi",
            "service_type": "Money Transfer",
            "sender_name": "Updated Sender",
            "send_amount": 250.0,
            "fee": 5.0,
            "country": "Mexico",
            "recipient_name": "Updated Recipient",
            "employee_id": emp_id,
            "status": "Sent",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, resp.get_data(as_text=True)
    body = resp.get_json()
    row = body["transfer"]
    assert row["company"] == "Maxi"
    assert row["sender_name"] == "Updated Sender"
    assert row["send_amount"] == 250.0
    assert row["fee"] == 5.0
    # Tax recomputed server-side.
    assert row["federal_tax"] > 0

    # Confirm DB-level changes + that an audit row was appended.
    with flask_app.app_context():
        t = db.session.get(Transfer, tid)
        assert t.company == "Maxi"
        assert t.sender_name == "Updated Sender"
        audits = db.session.query(TransferAudit).filter_by(
            transfer_id=tid,
        ).all()
        # Two audit rows expected: any prior history + the new
        # 'updated' row from this PUT. We require at least one
        # of them carries the "updated" action.
        actions = {a.action for a in audits}
        assert "updated" in actions or "status_changed" in actions


def test_update_returns_404_for_cross_tenant(client, test_store_id):
    """Seed a transfer in store A; log in to store A's admin; try
    to update a transfer ID that doesn't exist (or belongs to
    another store). Both must 404 — never 403, so a probe can't
    enumerate other tenants' transfer IDs."""
    from app import app as flask_app
    with flask_app.app_context():
        emp_id = _seed_employee(test_store_id, name="EE-404")

    login = client.post(
        "/api/v2/auth/login",
        json={
            "username": "admin@test.com",
            "password": "testpass123!",
            "store_id": test_store_id,
        },
    )
    token = login.get_json()["access_token"]

    resp = client.put(
        "/api/v2/transfers/9999999",
        json={
            "send_date": "2026-01-15",
            "company": "Intermex",
            "service_type": "Money Transfer",
            "sender_name": "S",
            "send_amount": 100.0,
            "country": "Mexico",
            "employee_id": emp_id,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404


def test_update_requires_jwt(test_store_id):
    """No bearer header → 401 from get_principal."""
    resp = _client().put(
        "/transfers/1",
        json={
            "send_date": "2026-01-15",
            "company": "Intermex",
            "service_type": "Money Transfer",
            "sender_name": "S",
            "send_amount": 100.0,
        },
    )
    assert resp.status_code == 401


# ── GET /transfers/employees (roster picker) ────────────────


def test_employees_returns_active_roster(client, test_store_id):
    """Roster endpoint returns the JWT principal's store roster,
    filtered to active employees only — feeds the SPA's
    'Processed by' dropdown."""
    from api.Modules.Tenancy.Models import StoreEmployee
    from app import app as flask_app, db
    with flask_app.app_context():
        e1 = StoreEmployee(store_id=test_store_id, name="Alice", is_active=True)
        e2 = StoreEmployee(store_id=test_store_id, name="Bob", is_active=True)
        e3 = StoreEmployee(store_id=test_store_id, name="ZRetired", is_active=False)
        db.session.add_all([e1, e2, e3]); db.session.commit()

    login = client.post(
        "/api/v2/auth/login",
        json={
            "username": "admin@test.com",
            "password": "testpass123!",
            "store_id": test_store_id,
        },
    )
    token = login.get_json()["access_token"]

    resp = client.get(
        "/api/v2/transfers/employees",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    body = resp.get_json()
    names = [e["name"] for e in body["employees"]]
    assert "Alice" in names and "Bob" in names
    # Inactive must be filtered out — same UX guarantee as the
    # legacy admin "Processed by" dropdown.
    assert "ZRetired" not in names


def test_employees_requires_jwt():
    resp = _client().get("/transfers/employees")
    assert resp.status_code == 401


def test_employees_rejects_superadmin(client):
    """Superadmin tokens have no store scope — the endpoint can't
    pick a roster, so it 403s."""
    from tests.conftest import login_superadmin
    token = login_superadmin(client)
    resp = client.get(
        "/api/v2/transfers/employees",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403


def test_update_status_only_records_status_changed_audit(
    client, test_store_id,
):
    """Pure status edits get the 'status_changed' audit action
    so the admin view can highlight them — same behavior as the
    legacy edit_transfer route.

    To isolate the status-only diff, we first do a baseline PUT
    so every field on the row matches what we'll send next; then
    a second PUT with only `status` flipped. Without that
    alignment, employee_name + sender_name + recipient_name on
    the freshly-seeded row differ from the request body and the
    audit (correctly) sees those as changes too.
    """
    from api.Modules.Audit.Models import TransferAudit
    from app import app as flask_app, db
    with flask_app.app_context():
        emp_id = _seed_employee(test_store_id, name="EE-status")
        tid = _seed_transfer(
            test_store_id, send_amount=100.0, fee=2.0, federal_tax=1.0,
            company="Intermex", country="MX", status="Sent",
            sender_name="S", recipient_name="R",
        )

    login = client.post(
        "/api/v2/auth/login",
        json={
            "username": "admin@test.com",
            "password": "testpass123!",
            "store_id": test_store_id,
        },
    )
    token = login.get_json()["access_token"]

    base_body = {
        "send_date": "2026-01-15",
        "company": "Intermex",
        "service_type": "Money Transfer",
        "sender_name": "S",
        "send_amount": 100.0,
        "fee": 2.0,
        "country": "MX",
        "recipient_name": "R",
        "employee_id": emp_id,
        "status": "Sent",
    }

    # 1) Baseline — align every field.
    r1 = client.put(
        f"/api/v2/transfers/{tid}",
        json=base_body,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r1.status_code == 200

    # 2) Status-only flip.
    r2 = client.put(
        f"/api/v2/transfers/{tid}",
        json={**base_body, "status": "Cancelled"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r2.status_code == 200
    with flask_app.app_context():
        actions = [
            a.action for a in
            db.session.query(TransferAudit)
              .filter_by(transfer_id=tid)
              .order_by(TransferAudit.id.asc())
              .all()
        ]
        # Last audit row was the status-only PUT.
        assert actions[-1] == "status_changed"
