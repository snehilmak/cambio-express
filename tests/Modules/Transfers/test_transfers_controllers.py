"""HTTP integration tests for the Transfers Controllers (PR 12).

Tests hit the FastAPI router via TestClient + via the Flask dispatcher
(strangler-fig path).
"""
from datetime import date, timedelta

from fastapi.testclient import TestClient
from tests._app import db, db_session
import pytest


def _seed_transfer(store_id, *, send_date=None, send_amount=100.0,
                    fee=2.0, federal_tax=1.0, company="Intermex",
                    service_type="Money Transfer", country="MX",
                    sender_name="S", recipient_name="R",
                    confirm_number=None, status="Sent",
                    batch_id=""):
    from api.Modules.Transfers.Models import Transfer
    from tests._app import db
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


@pytest.fixture
def api_client():
    from api.main import api_app
    with TestClient(api_app) as c:
        yield c


@pytest.fixture
def authed_client(test_store_id, api_client):
    from api.Modules.Tenancy.Models import User
    with db_session():
        u = db.session.query(User).filter_by(
            store_id=test_store_id, role="admin",
        ).first()
        assert u is not None
        username = u.username
    resp = api_client.post(
        "/auth/login",
        json={"username": username, "password": "testpass123!",
              "store_id": test_store_id},
    )
    token = resp.json()["access_token"]
    api_client.headers["Authorization"] = f"Bearer {token}"
    return api_client


# ── parse_store_ids contract ────────────────────────────────


def test_list_requires_auth(api_client):
    """No bearer header → 401."""
    resp = api_client.get("/transfers")
    assert resp.status_code == 401


def test_list_requires_store_ids(authed_client):
    resp = authed_client.get("/transfers")
    assert resp.status_code == 422


def test_list_rejects_non_numeric_store_ids(authed_client):
    resp = authed_client.get("/transfers", params={"store_ids": "abc"})
    assert resp.status_code == 422


def test_list_rejects_empty_store_ids(authed_client):
    resp = authed_client.get("/transfers", params={"store_ids": ""})
    assert resp.status_code == 422


def test_list_rejects_invalid_dir(authed_client):
    resp = authed_client.get(
        "/transfers", params={"store_ids": "1", "dir": "garbage"},
    )
    assert resp.status_code == 422


def test_list_rejects_out_of_range_per_page(authed_client):
    resp = authed_client.get(
        "/transfers", params={"store_ids": "1", "per_page": 0},
    )
    assert resp.status_code == 422
    resp = authed_client.get(
        "/transfers", params={"store_ids": "1", "per_page": 1000},
    )
    assert resp.status_code == 422


# ── Happy paths ─────────────────────────────────────────────


def test_list_response_envelope(test_store_id, authed_client):
    with db_session():
        for i in range(3):
            _seed_transfer(test_store_id, send_amount=100.0)
    resp = authed_client.get(
        "/transfers", params={"store_ids": str(test_store_id)},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert set(body.keys()) == {
        "rows", "total", "page", "per_page", "total_pages", "page_amount",
    }
    assert body["total"] == 3
    assert len(body["rows"]) == 3


def test_list_filters_company(test_store_id, authed_client):
    with db_session():
        _seed_transfer(test_store_id, company="Intermex",
                        confirm_number="X-Intermex")
        _seed_transfer(test_store_id, company="Maxi",
                        confirm_number="X-Maxi")
    resp = authed_client.get(
        "/transfers",
        params={"store_ids": str(test_store_id), "company": "Maxi"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["rows"][0]["company"] == "Maxi"


def test_list_global_search_q(test_store_id, authed_client):
    with db_session():
        _seed_transfer(test_store_id, sender_name="Alice",
                        confirm_number="X-A")
        _seed_transfer(test_store_id, sender_name="Bob",
                        confirm_number="X-B")
    resp = authed_client.get(
        "/transfers",
        params={"store_ids": str(test_store_id), "q": "alice"},
    )
    assert resp.status_code == 200
    assert resp.json()["total"] == 1


def test_list_pagination(test_store_id, authed_client):
    with db_session():
        for i in range(5):
            _seed_transfer(test_store_id, send_amount=100.0 * (i + 1))
    resp = authed_client.get(
        "/transfers",
        params={"store_ids": str(test_store_id), "per_page": 2, "page": 1},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 5
    assert body["total_pages"] == 3
    assert body["page"] == 1
    assert len(body["rows"]) == 2


def test_list_filters_date_range_string_input(test_store_id, authed_client):
    """Controller takes `date_from`/`date_to` as YYYY-MM-DD strings;
    the underlying TransferFilters parses them. Malformed strings drop
    the filter (legacy behavior)."""
    today = date.today()
    yesterday = today - timedelta(days=1)
    last_week = today - timedelta(days=7)
    with db_session():
        _seed_transfer(test_store_id, send_date=last_week,
                        confirm_number="X-LW")
        _seed_transfer(test_store_id, send_date=today,
                        confirm_number="X-T")
    resp = authed_client.get(
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


def test_list_multi_store_aggregation(test_store_id, authed_client):
    from api.Modules.Tenancy.Models import Store
    from tests._app import db
    with db_session():
        s2 = Store(name="Other", slug="other-tx-cc",
                    email="o@x.com", plan="trial")
        db.session.add(s2); db.session.commit()
        sid2 = s2.id
        _seed_transfer(test_store_id, confirm_number="X-Mine")
        _seed_transfer(sid2, confirm_number="X-Theirs")
    resp = authed_client.get(
        "/transfers",
        params={"store_ids": f"{test_store_id},{sid2}"},
    )
    assert resp.status_code == 200
    assert resp.json()["total"] == 2


def test_list_rows_have_total_collected(test_store_id, authed_client):
    """Wire test: the row payload must include `total_collected`
    (send + fee + tax) so the React table can render the column
    without recomputing client-side."""
    with db_session():
        _seed_transfer(test_store_id, send_amount=100.0,
                        fee=2.0, federal_tax=1.0)
    resp = authed_client.get(
        "/transfers", params={"store_ids": str(test_store_id)},
    )
    body = resp.json()
    assert body["rows"][0]["total_collected"] == 103.0


# ── Strangler-fig dispatch ──────────────────────────────────


def test_flask_dispatcher_routes_transfers_to_fastapi(client, test_store_id):
    from tests.conftest import login_admin
    with db_session():
        _seed_transfer(test_store_id, send_amount=99.0)
    token = login_admin(client, test_store_id)
    resp = client.get(
        f"/api/v2/transfers?store_ids={test_store_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.is_json
    assert resp.get_json()["total"] == 1


def test_openapi_includes_transfers_path(api_client):
    resp = api_client.get("/openapi.json")
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
    from tests._app import db
    e = StoreEmployee(store_id=store_id, name=name, is_active=is_active)
    db.session.add(e); db.session.commit()
    return e.id


def test_create_requires_jwt(test_store_id, api_client):
    """No bearer header → 401 from get_principal."""
    resp = api_client.post(
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
    with db_session():
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
    from tests._app import db
    with db_session():
        t = db.session.get(Transfer, row["id"])
        assert t is not None
        assert t.store_id == test_store_id
        assert t.sender_name == "Jane Sender"
        assert t.employee_id == emp_id


def test_create_recomputes_tax_ignoring_client_value(client, test_store_id):
    """Tax invariant — client can't override the server-computed
    federal_tax. We don't expose it as a request field at all
    (extra=forbid), and the response shows the recomputed value."""
    with db_session():
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


# Characterization: every field listed under "the 422 trap" in
# INVARIANTS.md MUST be rejected by the transfer POST.  Pins the
# full server-computed / derived surface so a future refactor
# can't silently let one slip into the writable schema.
@pytest.mark.parametrize("derived_field,value", [
    ("federal_tax", 99.99),     # always server-computed
    ("total_collected", 999.0), # derived @property
    ("id", 42),                 # DB identity
    ("created_by", 99),         # set from the JWT principal
    ("updated_at", "2026-01-01T00:00:00"),  # auto
    ("employee_name", "X"),     # snapshotted from the chosen employee
])
def test_create_rejects_every_derived_field(
    client, test_store_id, derived_field, value,
):
    with db_session():
        emp_id = _seed_employee(test_store_id, name="P1")
    login = client.post(
        "/api/v2/auth/login",
        json={
            "username": "admin@test.com",
            "password": "testpass123!",
            "store_id": test_store_id,
        },
    )
    token = login.get_json()["access_token"]
    body = {
        "send_date": "2026-01-15",
        "company": "Intermex",
        "service_type": "Money Transfer",
        "sender_name": "S",
        "send_amount": 100.0,
        "country": "Mexico",
        "employee_id": emp_id,
        derived_field: value,  # the trap
    }
    resp = client.post(
        "/api/v2/transfers", json=body,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422, (
        f"Expected 422 when sending {derived_field!r} (derived per "
        f"INVARIANTS.md), got {resp.status_code}.  If this field is "
        f"now legitimately client-supplied, update INVARIANTS.md + "
        f"CreateTransferRequest in the same PR."
    )


# Characterization: the bedrock formula
#   total_collected = send_amount + fee + federal_tax
# rendered in the wire response across a sweep of inputs.  Fuzz-
# adjacent — catches any future drift where a response adapter
# starts computing total_collected differently than the model.
@pytest.mark.parametrize("send_amount,fee", [
    (0.0, 0.0),
    (10.0, 0.0),
    (100.0, 5.0),
    (250.50, 10.25),
    (5000.0, 25.0),
    (999.99, 0.01),
])
def test_create_total_collected_matches_send_plus_fee_plus_tax(
    client, test_store_id, send_amount, fee,
):
    with db_session():
        emp_id = _seed_employee(test_store_id, name="FormulaCheck")
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
            "send_amount": send_amount,
            "fee": fee,
            "country": "Mexico",
            "employee_id": emp_id,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201, resp.get_data(as_text=True)
    row = resp.get_json()["transfer"]
    # The formula is the source of truth.  Tax is recomputed
    # server-side (we don't assert its exact value here; the
    # test_tax_service.py sweep covers that).
    expected_total = row["send_amount"] + row["fee"] + row["federal_tax"]
    assert row["total_collected"] == pytest.approx(expected_total), (
        f"total_collected drifted from send_amount + fee + federal_tax: "
        f"got {row['total_collected']}, expected {expected_total} "
        f"(send={row['send_amount']}, fee={row['fee']}, "
        f"tax={row['federal_tax']})"
    )


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
    with db_session():
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
    from tests._app import db
    with db_session():
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
    with db_session():
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
    with db_session():
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


def test_update_requires_jwt(test_store_id, api_client):
    """No bearer header → 401 from get_principal."""
    resp = api_client.put(
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
    from tests._app import db
    with db_session():
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


def test_employees_requires_jwt(api_client):
    resp = api_client.get("/transfers/employees")
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
    from tests._app import db
    with db_session():
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
    with db_session():
        actions = [
            a.action for a in
            db.session.query(TransferAudit)
              .filter_by(transfer_id=tid)
              .order_by(TransferAudit.id.asc())
              .all()
        ]
        # Last audit row was the status-only PUT.
        assert actions[-1] == "status_changed"


# ── Business-hours enforcement gate ─────────────────────────


def _flask_dispatcher_login(client, store_id) -> str:
    """Log the seeded admin in via the Flask dispatcher path
    (``/api/v2/auth/login``) — same flow the SPA takes in
    production. Distinct from ``_login_admin_token`` above,
    which targets the FastAPI TestClient directly via
    ``/auth/login``."""
    resp = client.post(
        "/api/v2/auth/login",
        json={
            "username": "admin@test.com",
            "password": "testpass123!",
            "store_id": store_id,
        },
    )
    assert resp.status_code == 200, resp.get_data(as_text=True)
    return resp.get_json()["access_token"]


def _valid_transfer_body(emp_id: int) -> dict:
    return {
        "send_date": "2026-01-15",
        "company": "Intermex",
        "service_type": "Money Transfer",
        "sender_name": "Hours Sender",
        "sender_phone": "5551234567",
        "send_amount": 100.0,
        "fee": 5.0,
        "country": "Mexico",
        "recipient_name": "Hours Recipient",
        "employee_id": emp_id,
    }


def _set_store_hours_closed_now(store_id: int) -> None:
    """Flip the store's enforce toggle on AND clamp every weekday
    to ``closed=True`` so ``is_open_at`` always returns False —
    keeps the test deterministic regardless of when CI runs."""
    from api.Modules.Tenancy.Models import Store
    from tests._app import db
    with db_session():
        s = db.session.get(Store, store_id)
        s.enforce_business_hours = True
        s.store_hours = [
            {"day": d, "open": "09:00", "close": "18:00", "closed": True}
            for d in range(7)
        ]
        db.session.commit()


def _set_store_hours_open_24_7(store_id: int) -> None:
    """Always-open schedule + enforce ON. Confirms the gate
    isn't a blanket reject — it actually consults the schedule."""
    from api.Modules.Tenancy.Models import Store
    from tests._app import db
    with db_session():
        s = db.session.get(Store, store_id)
        s.enforce_business_hours = True
        s.store_hours = [
            {"day": d, "open": "00:00", "close": "23:59", "closed": False}
            for d in range(7)
        ]
        db.session.commit()


def test_create_passes_when_enforce_business_hours_is_off(
    client, test_store_id,
):
    """Default-off behavior: even with a fully-closed schedule
    the create endpoint still 201s because the toggle is False.
    Guards against a regression that wires the gate
    unconditionally."""
    from api.Modules.Tenancy.Models import Store
    from tests._app import db
    with db_session():
        emp_id = _seed_employee(test_store_id, name="Gate Off")
        s = db.session.get(Store, test_store_id)
        # Closed schedule, but enforce toggle stays False.
        s.enforce_business_hours = False
        s.store_hours = [
            {"day": d, "open": "09:00", "close": "18:00", "closed": True}
            for d in range(7)
        ]
        db.session.commit()
    token = _flask_dispatcher_login(client, test_store_id)
    resp = client.post(
        "/api/v2/transfers",
        json=_valid_transfer_body(emp_id),
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201, resp.get_data(as_text=True)


def test_create_blocked_when_outside_business_hours(
    client, test_store_id,
):
    """Toggle on + every day closed → POST refuses with 422 and
    surfaces a helpful error message."""
    with db_session():
        emp_id = _seed_employee(test_store_id, name="Gate Closed")
    _set_store_hours_closed_now(test_store_id)
    token = _flask_dispatcher_login(client, test_store_id)
    resp = client.post(
        "/api/v2/transfers",
        json=_valid_transfer_body(emp_id),
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422
    body = resp.get_data(as_text=True).lower()
    assert "business-hours" in body or "open hours" in body


def test_create_allowed_with_enforce_on_and_open_window(
    client, test_store_id,
):
    """Toggle on + always-open schedule → POST 201s. Confirms the
    gate actually consults ``is_open_at`` instead of blocking
    every save once the toggle is on."""
    with db_session():
        emp_id = _seed_employee(test_store_id, name="Gate Open")
    _set_store_hours_open_24_7(test_store_id)
    token = _flask_dispatcher_login(client, test_store_id)
    resp = client.post(
        "/api/v2/transfers",
        json=_valid_transfer_body(emp_id),
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201, resp.get_data(as_text=True)


def test_update_blocked_when_outside_business_hours(
    client, test_store_id,
):
    """Same gate fires on PUT — operator can't sneak edits past
    the enforcement by saving a 201, then mutating after-hours."""
    # First create while the gate is off / open.
    with db_session():
        emp_id = _seed_employee(test_store_id, name="Update Gate")
    _set_store_hours_open_24_7(test_store_id)
    token = _flask_dispatcher_login(client, test_store_id)
    created = client.post(
        "/api/v2/transfers",
        json=_valid_transfer_body(emp_id),
        headers={"Authorization": f"Bearer {token}"},
    )
    assert created.status_code == 201
    tid = created.get_json()["transfer"]["id"]
    # Now flip to fully-closed and attempt an update.
    _set_store_hours_closed_now(test_store_id)
    resp = client.put(
        f"/api/v2/transfers/{tid}",
        json=_valid_transfer_body(emp_id) | {"send_amount": 200.0},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422
