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


def _seed_customer(store_id, *, full_name, phone_country="+1",
                    phone_number="", address=""):
    from api.Modules.Customers.Models import Customer
    from app import db
    c = Customer(
        store_id=store_id, full_name=full_name,
        phone_country=phone_country, phone_number=phone_number,
        address=address,
    )
    db.session.add(c); db.session.commit()
    return c.id


def _seed_owner(username="owner@x.com"):
    from api.Modules.Tenancy.Models import User
    from app import db
    u = User(username=username, full_name="Owner", role="owner")
    u.set_password("p")
    db.session.add(u); db.session.commit()
    return u.id


def _seed_store(slug, name="X"):
    from api.Modules.Tenancy.Models import Store
    from app import db
    s = Store(name=name, slug=slug, email=f"{slug}@x.com", plan="trial")
    db.session.add(s); db.session.commit()
    return s.id


def _link(owner_id, store_id):
    from api.Modules.Tenancy.Models import StoreOwnerLink
    from app import db
    l = StoreOwnerLink(owner_id=owner_id, store_id=store_id)
    db.session.add(l); db.session.commit()


def _client():
    from api.main import api_app
    return TestClient(api_app)


# ── /search ─────────────────────────────────────────────────


def test_search_requires_store_id():
    """`store_id` is a required Query — missing it must 422."""
    resp = _client().get("/customers/search", params={"q": "alice"})
    assert resp.status_code == 422


def test_search_short_query_returns_empty_envelope(test_store_id):
    from app import app as flask_app
    with flask_app.app_context():
        _seed_customer(test_store_id, full_name="Alice", phone_number="5550000")
    resp = _client().get(
        "/customers/search",
        params={"store_id": test_store_id, "q": "a"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body == {"matches": [], "suggestions": []}


def test_search_returns_envelope_with_matches(test_store_id):
    from app import app as flask_app
    with flask_app.app_context():
        _seed_customer(test_store_id, full_name="Alice Smith",
                        phone_country="+1", phone_number="5551234")
    resp = _client().get(
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


def test_search_decorates_cross_store_rows_with_home_name(test_store_id):
    """Customer logged at sibling store → row carries `home_store_name`
    so the UI can label it "from Store B"."""
    from app import app as flask_app, db
    with flask_app.app_context():
        oid = _seed_owner()
        s2_id = _seed_store("loc-2", name="Location 2")
        _link(oid, test_store_id)
        _link(oid, s2_id)
        _seed_customer(s2_id, full_name="Maria",
                        phone_country="+1", phone_number="5559999")
    resp = _client().get(
        "/customers/search",
        params={"store_id": test_store_id, "q": "maria"},
    )
    assert resp.status_code == 200
    matches = resp.json()["matches"]
    assert len(matches) == 1
    assert matches[0]["full_name"] == "Maria"
    assert matches[0]["home_store_name"] == "Location 2"
    assert matches[0]["home_store_id"] == s2_id


def test_search_excludes_stores_outside_umbrella(test_store_id):
    """Security property: a stranger store's customer must not leak
    through the autocomplete."""
    from app import app as flask_app
    with flask_app.app_context():
        s2_id = _seed_store("stranger")
        _seed_customer(s2_id, full_name="Hidden", phone_number="5550000")
    resp = _client().get(
        "/customers/search",
        params={"store_id": test_store_id, "q": "hidden"},
    )
    assert resp.status_code == 200
    assert resp.json()["matches"] == []


def test_search_fuzzy_suggestions_in_response(test_store_id):
    """A typo of an existing customer surfaces them under `suggestions`."""
    from app import app as flask_app
    with flask_app.app_context():
        _seed_customer(test_store_id, full_name="Maria Gonzalez",
                        phone_number="5551234")
    resp = _client().get(
        "/customers/search",
        params={"store_id": test_store_id, "q": "Maria Gonzales"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["matches"] == []
    assert any(c["full_name"] == "Maria Gonzalez"
                for c in body["suggestions"])


# ── /upsert ─────────────────────────────────────────────────


def test_upsert_creates_customer(test_store_id):
    body = {
        "full_name": "Alice",
        "phone_country": "+1",
        "phone_number": "5551234",
        "address": "123 Main",
    }
    resp = _client().post(
        "/customers/upsert",
        params={"store_id": test_store_id}, json=body,
    )
    assert resp.status_code == 200
    out = resp.json()["customer"]
    assert out["full_name"] == "Alice"
    assert out["phone_number"] == "5551234"
    assert out["address"] == "123 Main"
    assert out["home_store_id"] == test_store_id


def test_upsert_reuses_existing_phone(test_store_id):
    """Second upsert with same phone returns the same id."""
    from app import app as flask_app
    with flask_app.app_context():
        cid = _seed_customer(test_store_id, full_name="Alice Old",
                              phone_number="5551234")
    resp = _client().post(
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


def test_upsert_rejects_invalid_dob(test_store_id):
    resp = _client().post(
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


def test_upsert_accepts_well_formed_dob(test_store_id):
    resp = _client().post(
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


def test_upsert_rejects_extra_fields(test_store_id):
    """Pydantic schema sets `extra="forbid"` — typos in the request
    body should fail loudly instead of being silently dropped."""
    resp = _client().post(
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


def test_upsert_requires_full_name(test_store_id):
    resp = _client().post(
        "/customers/upsert",
        params={"store_id": test_store_id}, json={},
    )
    assert resp.status_code == 422


# ── Strangler-fig dispatch ──────────────────────────────────


def test_flask_dispatcher_routes_customers_to_fastapi(client, test_store_id):
    from app import app as flask_app
    with flask_app.app_context():
        _seed_customer(test_store_id, full_name="Alice",
                        phone_number="5551234")
    resp = client.get(
        f"/api/v2/customers/search?store_id={test_store_id}&q=alice",
    )
    assert resp.status_code == 200
    assert resp.is_json
    body = resp.get_json()
    assert len(body["matches"]) == 1


def test_openapi_includes_customer_paths():
    resp = _client().get("/openapi.json")
    assert resp.status_code == 200
    paths = set(resp.json()["paths"].keys())
    assert "/customers/search" in paths
    assert "/customers/upsert" in paths
