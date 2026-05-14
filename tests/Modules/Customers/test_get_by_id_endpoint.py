"""HTTP integration tests for GET /customers/{customer_id}."""
from fastapi.testclient import TestClient


def _seed_customer(store_id, *, full_name, phone_number=""):
    from api.Modules.Customers.Models import Customer
    from tests._app import db
    c = Customer(
        store_id=store_id, full_name=full_name,
        phone_country="+1", phone_number=phone_number,
    )
    db.session.add(c); db.session.commit()
    return c.id


def _seed_owner(username="owner-cgbi@x.com"):
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


def _client():
    from api.main import api_app
    return TestClient(api_app)


def test_get_customer_returns_envelope(test_store_id):
    from tests._app import app as flask_app
    with flask_app.app_context():
        cid = _seed_customer(
            test_store_id, full_name="Alice", phone_number="5551234",
        )
    resp = _client().get(
        f"/customers/{cid}", params={"store_id": test_store_id},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["customer"]["id"] == cid
    assert body["customer"]["full_name"] == "Alice"
    assert body["customer"]["phone_number"] == "5551234"
    assert body["customer"]["home_store_id"] == test_store_id


def test_get_customer_404_for_missing(test_store_id):
    resp = _client().get(
        "/customers/99999", params={"store_id": test_store_id},
    )
    assert resp.status_code == 404


def test_get_customer_404_for_unrelated_store(test_store_id):
    """Stranger-store lookup returns 404 (the owner-umbrella security
    property — same as the search endpoint)."""
    from tests._app import app as flask_app
    with flask_app.app_context():
        s2 = _seed_store("stranger-cgbi")
        cid = _seed_customer(s2, full_name="Hidden")
    resp = _client().get(
        f"/customers/{cid}", params={"store_id": test_store_id},
    )
    assert resp.status_code == 404


def test_get_customer_finds_in_owner_umbrella(test_store_id):
    """Customer at sibling store under same owner is reachable, with
    `home_store_name` decoration so the UI can label "from Store X"."""
    from tests._app import app as flask_app
    with flask_app.app_context():
        oid = _seed_owner()
        s2 = _seed_store("loc-cgbi", name="Sibling Loc")
        _link(oid, test_store_id)
        _link(oid, s2)
        cid = _seed_customer(s2, full_name="Maria")
    resp = _client().get(
        f"/customers/{cid}", params={"store_id": test_store_id},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["customer"]["full_name"] == "Maria"
    assert body["customer"]["home_store_id"] == s2
    assert body["customer"]["home_store_name"] == "Sibling Loc"


def test_get_customer_requires_store_id(test_store_id):
    from tests._app import app as flask_app
    with flask_app.app_context():
        cid = _seed_customer(test_store_id, full_name="Alice")
    resp = _client().get(f"/customers/{cid}")
    assert resp.status_code == 422


def test_get_customer_rejects_zero_id(test_store_id):
    resp = _client().get(
        "/customers/0", params={"store_id": test_store_id},
    )
    assert resp.status_code == 422


def test_openapi_includes_get_path():
    resp = _client().get("/openapi.json")
    paths = set(resp.json()["paths"].keys())
    assert "/customers/{customer_id}" in paths
