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


# ── /search ─────────────────────────────────────────────────


def test_search_requires_store_id(api_client):
    """`store_id` is a required Query — missing it must 422."""
    resp = api_client.get("/customers/search", params={"q": "alice"})
    assert resp.status_code == 422


def test_search_short_query_returns_empty_envelope(test_store_id, api_client):
    with db_session():
        _seed_customer(test_store_id, full_name="Alice", phone_number="5550000")
    resp = api_client.get(
        "/customers/search",
        params={"store_id": test_store_id, "q": "a"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body == {"matches": [], "suggestions": []}


def test_search_returns_envelope_with_matches(test_store_id, api_client):
    with db_session():
        _seed_customer(test_store_id, full_name="Alice Smith",
                        phone_country="+1", phone_number="5551234")
    resp = api_client.get(
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


def test_search_decorates_cross_store_rows_with_home_name(test_store_id, api_client):
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
    resp = api_client.get(
        "/customers/search",
        params={"store_id": test_store_id, "q": "maria"},
    )
    assert resp.status_code == 200
    matches = resp.json()["matches"]
    assert len(matches) == 1
    assert matches[0]["full_name"] == "Maria"
    assert matches[0]["home_store_name"] == "Location 2"
    assert matches[0]["home_store_id"] == s2_id


def test_search_excludes_stores_outside_umbrella(test_store_id, api_client):
    """Security property: a stranger store's customer must not leak
    through the autocomplete."""
    with db_session():
        s2_id = _seed_store("stranger")
        _seed_customer(s2_id, full_name="Hidden", phone_number="5550000")
    resp = api_client.get(
        "/customers/search",
        params={"store_id": test_store_id, "q": "hidden"},
    )
    assert resp.status_code == 200
    assert resp.json()["matches"] == []


def test_search_fuzzy_suggestions_in_response(test_store_id, api_client):
    """A typo of an existing customer surfaces them under `suggestions`."""
    with db_session():
        _seed_customer(test_store_id, full_name="Maria Gonzalez",
                        phone_number="5551234")
    resp = api_client.get(
        "/customers/search",
        params={"store_id": test_store_id, "q": "Maria Gonzales"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["matches"] == []
    assert any(c["full_name"] == "Maria Gonzalez"
                for c in body["suggestions"])


# ── /upsert ─────────────────────────────────────────────────


def test_upsert_creates_customer(test_store_id, api_client):
    body = {
        "full_name": "Alice",
        "phone_country": "+1",
        "phone_number": "5551234",
        "address": "123 Main",
    }
    resp = api_client.post(
        "/customers/upsert",
        params={"store_id": test_store_id}, json=body,
    )
    assert resp.status_code == 200
    out = resp.json()["customer"]
    assert out["full_name"] == "Alice"
    assert out["phone_number"] == "5551234"
    assert out["address"] == "123 Main"
    assert out["home_store_id"] == test_store_id


def test_upsert_reuses_existing_phone(test_store_id, api_client):
    """Second upsert with same phone returns the same id."""
    with db_session():
        cid = _seed_customer(test_store_id, full_name="Alice Old",
                              phone_number="5551234")
    resp = api_client.post(
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


def test_upsert_rejects_invalid_dob(test_store_id, api_client):
    resp = api_client.post(
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


def test_upsert_accepts_well_formed_dob(test_store_id, api_client):
    resp = api_client.post(
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


def test_upsert_rejects_extra_fields(test_store_id, api_client):
    """Pydantic schema sets `extra="forbid"` — typos in the request
    body should fail loudly instead of being silently dropped."""
    resp = api_client.post(
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


def test_upsert_requires_full_name(test_store_id, api_client):
    resp = api_client.post(
        "/customers/upsert",
        params={"store_id": test_store_id}, json={},
    )
    assert resp.status_code == 422


# ── Strangler-fig dispatch ──────────────────────────────────


def test_flask_dispatcher_routes_customers_to_fastapi(client, test_store_id):
    with db_session():
        _seed_customer(test_store_id, full_name="Alice",
                        phone_number="5551234")
    resp = client.get(
        f"/api/v2/customers/search?store_id={test_store_id}&q=alice",
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
