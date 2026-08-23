"""Catalog module (P2-1): vendors + price-book items.

The invariants under test:
  * vendor names unique per store (case-insensitive),
  * item scan codes unique per store; search matches name substring
    OR scan-code prefix; list uses the shared pagination envelope,
  * department / vendor links validate store ownership; 0 clears an
    optional link on update,
  * cashiers (employees) can read the catalog but not manage it,
  * module flag bundles: price_book ON for cstore, OFF for msb_hybrid.
"""
from tests._app import db, db_session
from tests.conftest import login_admin, make_employee_client


def _headers(token):
    return {"Authorization": f"Bearer {token}"}


def _admin(client, test_store_id):
    return _headers(login_admin(client, test_store_id))


def _mk_vendor(client, h, name="Frio Distributing", **overrides):
    body = {"name": name}
    body.update(overrides)
    resp = client.post("/api/v2/catalog/vendors", headers=h, json=body)
    assert resp.status_code == 201, resp.text
    return resp.json()["vendor"]


def _mk_item(client, h, pos_code="012345678905", name="Energy drink",
             **overrides):
    body = {"pos_code": pos_code, "name": name, "price": 2.99}
    body.update(overrides)
    resp = client.post("/api/v2/catalog/items", headers=h, json=body)
    assert resp.status_code == 201, resp.text
    return resp.json()["item"]


# ── Vendors ────────────────────────────────────────────────


def test_vendor_crud_roundtrip(client, test_store_id):
    h = _admin(client, test_store_id)
    vendor = _mk_vendor(
        client, h, "Gulf Coast Wholesale",
        contact_name="Maria", phone="555-0100",
        account_number="AC-2231",
    )
    assert vendor["account_number"] == "AC-2231"

    resp = client.put(
        f"/api/v2/catalog/vendors/{vendor['id']}", headers=h,
        json={"phone": "555-0199", "is_active": False},
    )
    assert resp.status_code == 200
    assert resp.json()["vendor"]["phone"] == "555-0199"
    # Inactive vendors drop out of the default list.
    assert client.get(
        "/api/v2/catalog/vendors", headers=h,
    ).json()["vendors"] == []
    assert len(client.get(
        "/api/v2/catalog/vendors?include_inactive=1", headers=h,
    ).json()["vendors"]) == 1


def test_duplicate_vendor_name_conflicts(client, test_store_id):
    h = _admin(client, test_store_id)
    _mk_vendor(client, h, "Metro Foods")
    resp = client.post("/api/v2/catalog/vendors", headers=h, json={
        "name": "metro foods",
    })
    assert resp.status_code == 409


def test_vendor_item_count(client, test_store_id):
    h = _admin(client, test_store_id)
    vendor = _mk_vendor(client, h, "Beverage Co")
    _mk_item(client, h, "111", "Cola", vendor_id=vendor["id"])
    _mk_item(client, h, "222", "Root beer", vendor_id=vendor["id"])
    rows = client.get(
        "/api/v2/catalog/vendors", headers=h,
    ).json()["vendors"]
    assert rows[0]["item_count"] == 2


# ── Items ──────────────────────────────────────────────────


def test_item_crud_and_search(client, test_store_id):
    h = _admin(client, test_store_id)
    _mk_item(client, h, "012345678905", "Monster Energy 16oz")
    _mk_item(client, h, "2", "7lb ice bag", pos_code_format="plu",
             price=2.99)

    # Name substring match.
    body = client.get(
        "/api/v2/catalog/items?q=energy", headers=h,
    ).json()
    assert body["total"] == 1
    assert body["rows"][0]["name"] == "Monster Energy 16oz"
    assert set(body) == {"rows", "total", "page", "total_pages"}

    # Scan-code prefix match.
    body = client.get("/api/v2/catalog/items?q=0123", headers=h).json()
    assert body["total"] == 1
    assert body["rows"][0]["pos_code"] == "012345678905"

    # Update price + deactivate; inactive drops from default list.
    item_id = body["rows"][0]["id"]
    resp = client.put(
        f"/api/v2/catalog/items/{item_id}", headers=h,
        json={"price": 3.49, "is_active": False},
    )
    assert resp.status_code == 200
    assert resp.json()["item"]["price"] == 3.49
    assert client.get(
        "/api/v2/catalog/items", headers=h,
    ).json()["total"] == 1  # only the ice bag remains active


def test_duplicate_pos_code_conflicts(client, test_store_id):
    h = _admin(client, test_store_id)
    _mk_item(client, h, "4900001", "Green tea")
    resp = client.post("/api/v2/catalog/items", headers=h, json={
        "pos_code": "4900001", "name": "Different item",
    })
    assert resp.status_code == 409


def test_item_links_validate_and_clear(client, test_store_id):
    h = _admin(client, test_store_id)
    dept = client.post("/api/v2/dayclose/departments", headers=h, json={
        "name": "Beverages",
    }).json()["department"]
    vendor = _mk_vendor(client, h, "Beverage Co")
    item = _mk_item(
        client, h, "333", "Spring water",
        department_id=dept["id"], vendor_id=vendor["id"],
    )
    assert item["department_name"] == "Beverages"
    assert item["vendor_name"] == "Beverage Co"

    # A department id from another store's space 404s.
    resp = client.post("/api/v2/catalog/items", headers=h, json={
        "pos_code": "444", "name": "Bad link", "department_id": 999999,
    })
    assert resp.status_code == 404

    # 0 clears an optional link on update.
    resp = client.put(
        f"/api/v2/catalog/items/{item['id']}", headers=h,
        json={"vendor_id": 0},
    )
    assert resp.status_code == 200
    assert resp.json()["item"]["vendor_id"] is None
    assert resp.json()["item"]["department_id"] == dept["id"]


def test_employee_reads_but_cannot_manage(client, test_store_id):
    h = _admin(client, test_store_id)
    _mk_item(client, h, "555", "Chips")
    emp, etok = make_employee_client(test_store_id)
    eh = _headers(etok)
    assert emp.get("/api/v2/catalog/items", headers=eh).status_code == 200
    assert emp.post("/api/v2/catalog/vendors", headers=eh, json={
        "name": "Nope Inc",
    }).status_code == 403
    assert emp.post("/api/v2/catalog/items", headers=eh, json={
        "pos_code": "666", "name": "Nope",
    }).status_code == 403


def test_price_book_bundle_by_business_type(client, test_store_id):
    from api.Modules.Billing.Services.feature_flags import (
        store_feature_enabled,
    )
    from api.Modules.Tenancy.Models import Store
    with db_session():
        store = db.session.get(Store, test_store_id)
        for btype, expected in (
            ("cstore", True), ("gas_station", True),
            ("grocery", True), ("msb_hybrid", False),
        ):
            store.business_type = btype
            assert store_feature_enabled(
                db.session, store, "module_price_book",
            ) is expected, btype
