"""HTTP integration tests for the Customers Controllers (PR 8).

Hits the FastAPI router two ways:
  1. `TestClient(api_app)` directly (route paths relative).
  2. The Flask test client through `DispatcherMiddleware` to prove
     the strangler-fig dispatch still works.

Service-level behavior is unit-tested in `test_customers_services.py`.
This file pins the controller contract — query parsing, response
envelope, status codes.
"""
from datetime import date

from fastapi.testclient import TestClient
from tests._app import db, db_session
import pytest


def _seed_customer(store_id, *, full_name, phone_country="+1",
                    phone_number="", address=""):
    from api.Modules.Customers.Models import Customer
    from tests._app import db
    c = Customer(
        store_id=store_id, full_name=full_name,
        phone_country=phone_country, phone_number=phone_number,
        address=address,
    )
    db.session.add(c); db.session.commit()
    return c.id


def _seed_owner(username="owner@x.com"):
    from api.Modules.Tenancy.Models import User
    from tests._app import db
    u = User(username=username, full_name="Owner", role="owner")
    u.set_password("p")
    db.session.add(u); db.session.commit()
    return u.id


def _seed_store(slug, name="X"):
    from api.Modules.Tenancy.Models import Store
    from tests._app import db
    s = Store(name=name, slug=slug, email=f"{slug}@x.com", plan="trial")
    db.session.add(s); db.session.commit()
    return s.id


def _link(owner_id, store_id):
    from api.Modules.Tenancy.Models import StoreOwnerLink
    from tests._app import db
    l = StoreOwnerLink(owner_id=owner_id, store_id=store_id)
    db.session.add(l); db.session.commit()


@pytest.fixture
def api_client():
    from api.main import api_app
    with TestClient(api_app) as c:
        yield c


@pytest.fixture
def authed_client(test_store_id, api_client):
    """TestClient with admin auth headers injected."""
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


# ── /search ─────────────────────────────────────────────────


def test_search_requires_auth(api_client):
    """Search requires authentication — missing auth must 401."""
    resp = api_client.get("/customers/search", params={"q": "alice"})
    assert resp.status_code == 401


def test_search_short_query_returns_empty_envelope(test_store_id, authed_client):
    with db_session():
        _seed_customer(test_store_id, full_name="Alice", phone_number="5550000")
    resp = authed_client.get(
        "/customers/search",
        params={"store_id": test_store_id, "q": "a"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body == {"matches": [], "suggestions": []}


def test_search_returns_envelope_with_matches(test_store_id, authed_client):
    with db_session():
        _seed_customer(test_store_id, full_name="Alice Smith",
                        phone_country="+1", phone_number="5551234")
    resp = authed_client.get(
        "/customers/search",
        params={"store_id": test_store_id, "q": "alice"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert set(body.keys()) == {"matches", "suggestions"}
    assert len(body["matches"]) == 1
    row = body["matches"][0]
    assert row["full_name"] == "Alice Smith"
    assert row["phone_country"] == "+1"
    assert row["phone_number"] == "5551234"
    # current store → no home_store_name decoration
    assert row["home_store_name"] == ""
    assert row["home_store_id"] == test_store_id


def test_search_decorates_cross_store_rows_with_home_name(test_store_id, authed_client):
    """Customer logged at sibling store → row carries `home_store_name`
    so the UI can label it "from Store B"."""
    from tests._app import db
    with db_session():
        oid = _seed_owner()
        s2_id = _seed_store("loc-2", name="Location 2")
        _link(oid, test_store_id)
        _link(oid, s2_id)
        _seed_customer(s2_id, full_name="Maria",
                        phone_country="+1", phone_number="5559999")
    resp = authed_client.get(
        "/customers/search",
        params={"store_id": test_store_id, "q": "maria"},
    )
    assert resp.status_code == 200
    matches = resp.json()["matches"]
    assert len(matches) == 1
    assert matches[0]["full_name"] == "Maria"
    assert matches[0]["home_store_name"] == "Location 2"
    assert matches[0]["home_store_id"] == s2_id


def test_search_excludes_stores_outside_umbrella(test_store_id, authed_client):
    """Security property: a stranger store's customer must not leak
    through the autocomplete."""
    with db_session():
        s2_id = _seed_store("stranger")
        _seed_customer(s2_id, full_name="Hidden", phone_number="5550000")
    resp = authed_client.get(
        "/customers/search",
        params={"store_id": test_store_id, "q": "hidden"},
    )
    assert resp.status_code == 200
    assert resp.json()["matches"] == []


def test_search_fuzzy_suggestions_in_response(test_store_id, authed_client):
    """A typo of an existing customer surfaces them under `suggestions`."""
    with db_session():
        _seed_customer(test_store_id, full_name="Maria Gonzalez",
                        phone_number="5551234")
    resp = authed_client.get(
        "/customers/search",
        params={"store_id": test_store_id, "q": "Maria Gonzales"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["matches"] == []
    assert any(c["full_name"] == "Maria Gonzalez"
                for c in body["suggestions"])


# ── /upsert ─────────────────────────────────────────────────


def test_upsert_creates_customer(test_store_id, authed_client):
    body = {
        "full_name": "Alice",
        "phone_country": "+1",
        "phone_number": "5551234",
        "address": "123 Main",
    }
    resp = authed_client.post(
        "/customers/upsert",
        params={"store_id": test_store_id}, json=body,
    )
    assert resp.status_code == 200
    out = resp.json()["customer"]
    assert out["full_name"] == "Alice"
    assert out["phone_number"] == "5551234"
    assert out["address"] == "123 Main"
    assert out["home_store_id"] == test_store_id


def test_upsert_reuses_existing_phone(test_store_id, authed_client):
    """Second upsert with same phone returns the same id."""
    with db_session():
        cid = _seed_customer(test_store_id, full_name="Alice Old",
                              phone_number="5551234")
    resp = authed_client.post(
        "/customers/upsert",
        params={"store_id": test_store_id},
        json={
            "full_name": "Alice New",
            "phone_country": "+1",
            "phone_number": "5551234",
        },
    )
    assert resp.status_code == 200
    out = resp.json()["customer"]
    assert out["id"] == cid
    assert out["full_name"] == "Alice New"


def test_upsert_rejects_invalid_dob(test_store_id, authed_client):
    resp = authed_client.post(
        "/customers/upsert",
        params={"store_id": test_store_id},
        json={
            "full_name": "Alice",
            "phone_country": "+1",
            "phone_number": "5551234",
            "dob": "not-a-date",
        },
    )
    assert resp.status_code == 422


def test_upsert_accepts_well_formed_dob(test_store_id, authed_client):
    resp = authed_client.post(
        "/customers/upsert",
        params={"store_id": test_store_id},
        json={
            "full_name": "Alice",
            "phone_country": "+1",
            "phone_number": "5551234",
            "dob": "1990-01-15",
        },
    )
    assert resp.status_code == 200
    assert resp.json()["customer"]["dob"] == "1990-01-15"


def test_upsert_rejects_extra_fields(test_store_id, authed_client):
    """Pydantic schema sets `extra="forbid"` — typos in the request
    body should fail loudly instead of being silently dropped."""
    resp = authed_client.post(
        "/customers/upsert",
        params={"store_id": test_store_id},
        json={
            "full_name": "Alice",
            "phone_country": "+1",
            "phone_number": "5551234",
            "garbagefield": "x",
        },
    )
    assert resp.status_code == 422


def test_upsert_requires_full_name(test_store_id, authed_client):
    resp = authed_client.post(
        "/customers/upsert",
        params={"store_id": test_store_id}, json={},
    )
    assert resp.status_code == 422


# ── Strangler-fig dispatch ──────────────────────────────────


def test_flask_dispatcher_routes_customers_to_fastapi(client, test_store_id):
    from tests.conftest import login_admin
    token = login_admin(client, test_store_id)
    with db_session():
        _seed_customer(test_store_id, full_name="Alice",
                        phone_number="5551234")
    resp = client.get(
        f"/api/v2/customers/search?store_id={test_store_id}&q=alice",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.is_json
    body = resp.get_json()
    assert len(body["matches"]) == 1


def test_openapi_includes_customer_paths(api_client):
    resp = api_client.get("/openapi.json")
    assert resp.status_code == 200
    paths = set(resp.json()["paths"].keys())
    assert "/customers/search" in paths
    assert "/customers/upsert" in paths
    assert "/customers/export.csv" in paths


# ── /export.csv ─────────────────────────────────────────────


def _login_admin(client, store_id):
    """Drive the password-login flow and return the JWT. Reused
    across the export-csv tests below."""
    resp = client.post(
        "/api/v2/auth/login",
        json={
            "username": "admin@test.com",
            "password": "testpass123!",
            "store_id": store_id,
        },
    )
    return resp.get_json()["access_token"]


def test_export_csv_requires_jwt(client):
    """No Authorization header → 401. Tenancy must come from the
    JWT, not from a query param, so unauth callers can't request
    another store's directory."""
    resp = client.get("/api/v2/customers/export.csv")
    assert resp.status_code == 401


def test_export_csv_rejects_cashier_role(client):
    """Employees can't dump the full directory — only admin /
    owner / superadmin can. Mirrors the tax-export ZIP gate."""
    from api.Modules.Tenancy.Models import User
    with db_session():
        u = User(
            store_id=None, username="emp_export_test",
            role="employee", is_active=True,
        )
        u.set_password("emppass1234")
        db.session.add(u); db.session.commit()
    try:
        login = client.post(
            "/api/v2/auth/login",
            json={
                "username": "emp_export_test",
                "password": "emppass1234",
                "store_id": None,
            },
        )
        token = login.get_json()["access_token"]
        resp = client.get(
            "/api/v2/customers/export.csv",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 403
    finally:
        with db_session():
            u2 = db.session.query(User).filter_by(
                username="emp_export_test",
            ).first()
            if u2:
                db.session.delete(u2); db.session.commit()


def test_export_csv_returns_text_csv_with_header(client, test_store_id):
    """Happy path: admin gets a ``text/csv`` response with the
    header row + one row per customer in the umbrella."""
    with db_session():
        _seed_customer(
            test_store_id,
            full_name="Alice Smith",
            phone_country="+1", phone_number="5551234567",
            address="123 Main St",
        )
        _seed_customer(
            test_store_id,
            full_name="Bob Jones",
            phone_country="+1", phone_number="5559876543",
            address="456 Oak Ave",
        )
    token = _login_admin(client, test_store_id)
    resp = client.get(
        "/api/v2/customers/export.csv",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/csv")
    assert "attachment" in resp.headers["content-disposition"]
    assert "customers_" in resp.headers["content-disposition"]
    body = resp.get_data(as_text=True)
    # Header row matches the spec the controller writes.
    first_line = body.splitlines()[0]
    assert first_line.startswith(
        "Full name,Phone country,Phone number,DOB,Address,Home store,",
    )
    # Alphabetical ordering — Alice before Bob.
    assert body.index("Alice Smith") < body.index("Bob Jones")
    # The data row carries phone + address verbatim.
    assert "5551234567" in body
    assert "123 Main St" in body


def test_export_csv_scoped_to_owner_umbrella(client, test_store_id):
    """A customer from a store outside the umbrella must NOT appear
    in the export — same isolation guarantee as the search route."""
    # Seed an unrelated store + a customer there.
    with db_session():
        from api.Modules.Tenancy.Models import Store
        outsider_store = Store(
            name="Outsider", slug="outsider",
            email="o@x.com", plan="trial",
        )
        db.session.add(outsider_store); db.session.commit()
        _seed_customer(
            outsider_store.id,
            full_name="Outsider Carol",
            phone_country="+1", phone_number="5550009999",
        )
    token = _login_admin(client, test_store_id)
    resp = client.get(
        "/api/v2/customers/export.csv",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "Outsider Carol" not in body
    assert "5550009999" not in body


def test_export_csv_empty_when_no_customers(client, test_store_id):
    """A brand-new store with no customers gets a CSV with only
    the header row — no error, no 404."""
    # The test fixture's store may have customers seeded by other
    # tests in the session; create a fresh admin user in a brand-
    # new store so this test is hermetic regardless of order.
    from api.Modules.Tenancy.Models import Store, User
    with db_session():
        s = Store(
            name="Empty Co", slug="empty-export-test",
            email="empty@x.com", plan="trial",
        )
        db.session.add(s); db.session.commit()
        new_store_id = s.id
        u = User(
            store_id=new_store_id, username="admin_empty_export",
            role="admin", is_active=True,
        )
        u.set_password("p123pass!")
        db.session.add(u); db.session.commit()
    try:
        login = client.post(
            "/api/v2/auth/login",
            json={
                "username": "admin_empty_export",
                "password": "p123pass!",
                "store_id": new_store_id,
            },
        )
        token = login.get_json()["access_token"]
        resp = client.get(
            "/api/v2/customers/export.csv",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        body = resp.get_data(as_text=True)
        # Header row only; no data lines.
        lines = [l for l in body.splitlines() if l.strip()]
        assert len(lines) == 1
        assert lines[0].startswith("Full name,Phone country,")
    finally:
        # Clean up the test-specific store + user so other tests'
        # store listings aren't polluted.
        with db_session():
            u2 = db.session.query(User).filter_by(
                username="admin_empty_export",
            ).first()
            s2 = db.session.query(Store).filter_by(
                slug="empty-export-test",
            ).first()
            if u2:
                db.session.delete(u2)
            if s2:
                db.session.delete(s2)
            db.session.commit()


# ── /{customer_id}/recent-recipients ─────────────────────────


def _seed_transfer_for_recipient(
    store_id, customer_id, *, recipient_name="Maria Lopez",
    country="Mexico", recipient_phone="5550001111",
    status="Sent",
):
    """Seed a Transfer row + the StoreEmployee FK it requires.
    The recent-recipients lookup groups by recipient_name/country/
    phone, so several call sites pass different values to test
    distinctness."""
    from datetime import date as _date
    from api.Modules.Transfers.Models import Transfer
    from api.Modules.Tenancy.Models import StoreEmployee
    emp = db.session.query(StoreEmployee).filter_by(
        store_id=store_id,
    ).first()
    if emp is None:
        emp = StoreEmployee(
            store_id=store_id, name="Test cashier", is_active=True,
        )
        db.session.add(emp); db.session.flush()
    t = Transfer(
        store_id=store_id,
        send_date=_date.today(),
        company="Intermex",
        service_type="Money Transfer",
        sender_name="Sender",
        sender_phone="5550000000",
        sender_phone_country="+1",
        sender_address="",
        send_amount=100.0,
        fee=5.0,
        federal_tax=0.0,
        country=country,
        recipient_name=recipient_name,
        recipient_phone=recipient_phone,
        confirm_number="",
        status=status,
        employee_id=emp.id,
        customer_id=customer_id,
    )
    db.session.add(t); db.session.commit()
    return t.id


def test_recent_recipients_returns_distinct_rows(test_store_id, authed_client):
    with db_session():
        cid = _seed_customer(test_store_id, full_name="Sender One")
        _seed_transfer_for_recipient(
            test_store_id, cid, recipient_name="Maria Lopez",
        )
        _seed_transfer_for_recipient(
            test_store_id, cid, recipient_name="Jose Garcia",
        )
        # Duplicate of Maria Lopez — should still be one row.
        _seed_transfer_for_recipient(
            test_store_id, cid, recipient_name="Maria Lopez",
        )
    resp = authed_client.get(
        f"/customers/{cid}/recent-recipients",
        params={"store_id": test_store_id},
    )
    assert resp.status_code == 200
    rows = resp.json()["rows"]
    names = sorted(r["name"] for r in rows)
    assert names == ["Jose Garcia", "Maria Lopez"]


def test_recent_recipients_excludes_canceled(test_store_id, authed_client):
    """Canceled / Rejected transfers don't surface — those aren't
    recipients the cashier would expect to reuse."""
    with db_session():
        cid = _seed_customer(test_store_id, full_name="Sender Two")
        _seed_transfer_for_recipient(
            test_store_id, cid, recipient_name="Live Person",
            status="Sent",
        )
        _seed_transfer_for_recipient(
            test_store_id, cid, recipient_name="Dead Person",
            status="Canceled",
        )
    resp = authed_client.get(
        f"/customers/{cid}/recent-recipients",
        params={"store_id": test_store_id},
    )
    rows = resp.json()["rows"]
    names = {r["name"] for r in rows}
    assert "Live Person" in names
    assert "Dead Person" not in names


def test_recent_recipients_unknown_customer_returns_empty(
    test_store_id, authed_client,
):
    """Unknown customer (or one outside the umbrella) returns an
    empty list, never 404. The SPA renders the empty case the same
    as "no history" — a 404 here would just be extra error handling."""
    resp = authed_client.get(
        "/customers/9999999/recent-recipients",
        params={"store_id": test_store_id},
    )
    assert resp.status_code == 200
    assert resp.json()["rows"] == []


def test_recent_recipients_respects_limit(test_store_id, authed_client):
    """``limit=2`` caps the result to 2 rows even when more
    distinct recipients exist."""
    with db_session():
        cid = _seed_customer(test_store_id, full_name="Sender Three")
        for i in range(4):
            _seed_transfer_for_recipient(
                test_store_id, cid, recipient_name=f"Recipient {i}",
            )
    resp = authed_client.get(
        f"/customers/{cid}/recent-recipients",
        params={"store_id": test_store_id, "limit": 2},
    )
    rows = resp.json()["rows"]
    assert len(rows) == 2


# ── /{winner_id}/merge ─────────────────────────────────────


def _seed_basic_transfer(store_id, customer_id, *, status="Sent"):
    """Tiny transfer row pinned to ``customer_id``. Used by the
    merge tests to verify FK re-pointing."""
    from datetime import date as _date
    from api.Modules.Transfers.Models import Transfer
    from api.Modules.Tenancy.Models import StoreEmployee
    emp = db.session.query(StoreEmployee).filter_by(
        store_id=store_id,
    ).first()
    if emp is None:
        emp = StoreEmployee(
            store_id=store_id, name="cashier", is_active=True,
        )
        db.session.add(emp); db.session.flush()
    t = Transfer(
        store_id=store_id,
        send_date=_date.today(),
        company="Intermex",
        service_type="Money Transfer",
        sender_name="Sender",
        sender_phone="5550000000",
        sender_phone_country="+1",
        sender_address="",
        send_amount=100.0,
        fee=5.0,
        federal_tax=0.0,
        country="Mexico",
        recipient_name="Recipient",
        recipient_phone="",
        confirm_number="",
        status=status,
        employee_id=emp.id,
        customer_id=customer_id,
    )
    db.session.add(t); db.session.commit()
    return t.id


def test_merge_requires_jwt(client):
    resp = client.post(
        "/api/v2/customers/1/merge", json={"loser_id": 2},
    )
    assert resp.status_code == 401


def test_merge_rejects_cashier_role(client, test_store_id):
    """Employees can't merge — destructive operation + audit trail
    needs admin attribution."""
    from api.Modules.Tenancy.Models import User
    with db_session():
        emp = User(
            store_id=test_store_id, username="cashier_merge@test.com",
            full_name="Cashier", role="employee",
        )
        emp.set_password("p123pass!")
        db.session.add(emp); db.session.commit()
    login = client.post(
        "/api/v2/auth/login",
        json={
            "username": "cashier_merge@test.com",
            "password": "p123pass!",
            "store_id": test_store_id,
        },
    )
    token = login.get_json()["access_token"]
    resp = client.post(
        "/api/v2/customers/1/merge",
        json={"loser_id": 2},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403


def test_merge_repoints_transfers_and_deletes_loser(
    client, test_store_id,
):
    """Happy path: two customers, transfers pinned to each, merge
    flips the loser's transfers onto the winner and deletes the
    loser row. Response carries the repointed count."""
    from api.Modules.Customers.Models import Customer
    from api.Modules.Transfers.Models import Transfer
    with db_session():
        winner_id = _seed_customer(
            test_store_id, full_name="Maria Lopez",
            phone_number="5551110000",
        )
        loser_id = _seed_customer(
            test_store_id, full_name="Maria Lopes",  # typo
            phone_number="5551111111",
        )
        _seed_basic_transfer(test_store_id, winner_id)
        _seed_basic_transfer(test_store_id, loser_id)
        _seed_basic_transfer(test_store_id, loser_id)
    token = _login_admin(client, test_store_id)
    resp = client.post(
        f"/api/v2/customers/{winner_id}/merge",
        json={"loser_id": loser_id},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, resp.get_data(as_text=True)
    body = resp.get_json()
    assert body["winner_id"] == winner_id
    assert body["loser_id"] == loser_id
    assert body["transfers_repointed"] == 2
    with db_session():
        # Loser row deleted.
        assert db.session.get(Customer, loser_id) is None
        # Every transfer now points at the winner.
        count = (
            db.session.query(Transfer)
              .filter_by(customer_id=winner_id)
              .count()
        )
        assert count == 3


def test_merge_records_operator_audit_entry(client, test_store_id):
    """CLAUDE.md invariant #7 (audit every operator mutation)."""
    from api.Modules.Audit.Models import OperatorAuditLog
    with db_session():
        winner_id = _seed_customer(
            test_store_id, full_name="Audit Winner",
            phone_number="5552220000",
        )
        loser_id = _seed_customer(
            test_store_id, full_name="Audit Loser",
            phone_number="5552220001",
        )
    token = _login_admin(client, test_store_id)
    resp = client.post(
        f"/api/v2/customers/{winner_id}/merge",
        json={"loser_id": loser_id},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    with db_session():
        rows = (
            db.session.query(OperatorAuditLog)
              .filter_by(target_type="customer", action="merge")
              .all()
        )
        # At least one entry referencing this merge.
        assert any(
            f"#{loser_id}" in (r.summary or "")
            and r.target_id == str(winner_id)
            for r in rows
        ), [r.summary for r in rows]


def test_merge_404_on_unknown_winner(client, test_store_id):
    with db_session():
        loser_id = _seed_customer(
            test_store_id, full_name="Lone Customer",
            phone_number="5559990000",
        )
    token = _login_admin(client, test_store_id)
    resp = client.post(
        "/api/v2/customers/9999999/merge",
        json={"loser_id": loser_id},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404


def test_merge_404_on_unknown_loser(client, test_store_id):
    with db_session():
        winner_id = _seed_customer(
            test_store_id, full_name="Lone Customer 2",
            phone_number="5559990001",
        )
    token = _login_admin(client, test_store_id)
    resp = client.post(
        f"/api/v2/customers/{winner_id}/merge",
        json={"loser_id": 9999999},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404


def test_merge_400_when_same_customer(client, test_store_id):
    with db_session():
        cid = _seed_customer(
            test_store_id, full_name="Self",
            phone_number="5559990002",
        )
    token = _login_admin(client, test_store_id)
    resp = client.post(
        f"/api/v2/customers/{cid}/merge",
        json={"loser_id": cid},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 400


def test_merge_rejects_customer_outside_umbrella(
    client, test_store_id,
):
    """A customer that exists but lives in an unrelated store
    looks 404 from inside this umbrella — never expose its
    existence."""
    from api.Modules.Tenancy.Models import Store
    with db_session():
        winner_id = _seed_customer(
            test_store_id, full_name="Mine",
            phone_number="5558880000",
        )
        # Customer at an unrelated store (no StoreOwnerLink between
        # it and test_store_id).
        unrelated = Store(
            name="Unrelated", slug="unrelated-merge",
            email="unrelated@x.com", plan="basic",
        )
        db.session.add(unrelated); db.session.flush()
        outside_id = _seed_customer(
            unrelated.id, full_name="Outsider",
            phone_number="5558880001",
        )
    token = _login_admin(client, test_store_id)
    resp = client.post(
        f"/api/v2/customers/{winner_id}/merge",
        json={"loser_id": outside_id},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404


def test_merge_rejects_extra_fields(client, test_store_id):
    """Pydantic ``extra="forbid"`` — typo'd field → 422."""
    token = _login_admin(client, test_store_id)
    resp = client.post(
        "/api/v2/customers/1/merge",
        json={"loser_id": 2, "extra": "nope"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422


def test_merge_rejects_missing_loser_id(client, test_store_id):
    token = _login_admin(client, test_store_id)
    resp = client.post(
        "/api/v2/customers/1/merge",
        json={},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422


def test_merge_owner_umbrella_succeeds(client, test_store_id):
    """A customer at a sibling store (linked via StoreOwnerLink to
    the caller's store via a shared owner) is mergeable — that's
    the whole point of the owner-umbrella scoping."""
    from api.Modules.Tenancy.Models import Store, StoreOwnerLink, User
    with db_session():
        # Sibling store + owner link.
        sibling = Store(
            name="Sibling", slug="sibling-merge",
            email="sib@x.com", plan="basic",
        )
        db.session.add(sibling); db.session.flush()
        owner = User(
            store_id=None, username="owner_merge@test.com",
            full_name="Owner", role="owner",
        )
        owner.set_password("pw")
        db.session.add(owner); db.session.flush()
        db.session.add_all([
            StoreOwnerLink(store_id=test_store_id, owner_id=owner.id),
            StoreOwnerLink(store_id=sibling.id, owner_id=owner.id),
        ])
        db.session.commit()
        winner_id = _seed_customer(
            test_store_id, full_name="Maria Lopez",
            phone_number="5557770000",
        )
        loser_id = _seed_customer(
            sibling.id, full_name="Maria Lopez 2",
            phone_number="5557770001",
        )
    token = _login_admin(client, test_store_id)
    resp = client.post(
        f"/api/v2/customers/{winner_id}/merge",
        json={"loser_id": loser_id},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, resp.get_data(as_text=True)
    body = resp.get_json()
    assert body["winner_id"] == winner_id
    assert body["loser_id"] == loser_id
