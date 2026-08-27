"""Purchase invoices (P3-1): vendor invoices + price-book cost feedback.

The invariants under test:
  * invoice numbers unique per (store, vendor) — different vendors
    can reuse the same numbering,
  * total = subtotal + tax + other (derived, never stored),
  * line totals default to quantity × unit cost; a keyed printed
    amount wins,
  * update_item_costs pushes linked line costs onto the price book
    (and only then),
  * marking paid → un-paid clears paid_on; lines replace-all on
    update,
  * list filters by vendor / status / invoice-number search with
    the shared pagination envelope,
  * cashiers can read but not manage invoices.
"""
from tests.conftest import login_admin, make_employee_client


def _headers(token):
    return {"Authorization": f"Bearer {token}"}


def _admin(client, test_store_id):
    return _headers(login_admin(client, test_store_id))


def _mk_vendor(client, h, name="Frio Distributing"):
    resp = client.post("/api/v2/catalog/vendors", headers=h, json={
        "name": name,
    })
    assert resp.status_code == 201, resp.text
    return resp.json()["vendor"]


def _mk_item(client, h, pos_code, name, cost=0.0):
    resp = client.post("/api/v2/catalog/items", headers=h, json={
        "pos_code": pos_code, "name": name, "price": 2.99, "cost": cost,
    })
    assert resp.status_code == 201, resp.text
    return resp.json()["item"]


def test_invoice_create_totals_and_line_math(client, test_store_id):
    h = _admin(client, test_store_id)
    vendor = _mk_vendor(client, h)
    item = _mk_item(client, h, "111", "Cola 20oz")

    resp = client.post("/api/v2/catalog/invoices", headers=h, json={
        "vendor_id": vendor["id"],
        "invoice_number": "INV-1001",
        "invoice_date": "2026-08-20",
        "due_date": "2026-09-05",
        "subtotal": 480.00,
        "tax": 12.40,
        "other": 7.60,
        "lines": [
            # Derived line total: 24 × $1.10 = $26.40.
            {"item_id": item["id"], "quantity": 24, "unit_cost": 1.10},
            # Keyed printed amount wins over 10 × $2.00.
            {"description": "CO2 tank refill", "quantity": 10,
             "unit_cost": 2.00, "line_total": 19.75},
        ],
    })
    assert resp.status_code == 201, resp.text
    body = resp.json()
    inv = body["invoice"]
    assert inv["vendor_name"] == "Frio Distributing"
    assert inv["total"] == 500.00          # 480 + 12.40 + 7.60
    assert inv["line_count"] == 2
    lines = {
        (line["item_id"], line["description"]): line
        for line in inv["lines"]
    }
    assert lines[(item["id"], "")]["line_total"] == 26.40
    assert lines[(None, "CO2 tank refill")]["line_total"] == 19.75
    assert lines[(item["id"], "")]["item_name"] == "Cola 20oz"
    # No cost feedback unless asked for.
    assert body["items_cost_updated"] == 0
    assert client.get(
        f"/api/v2/catalog/items?q=111", headers=h,
    ).json()["rows"][0]["cost"] == 0.0


def test_invoice_number_unique_per_vendor(client, test_store_id):
    h = _admin(client, test_store_id)
    v1 = _mk_vendor(client, h, "Vendor A")
    v2 = _mk_vendor(client, h, "Vendor B")
    base = {"invoice_number": "1000", "invoice_date": "2026-08-20"}
    assert client.post("/api/v2/catalog/invoices", headers=h, json={
        **base, "vendor_id": v1["id"],
    }).status_code == 201
    # Same number at the same vendor conflicts…
    assert client.post("/api/v2/catalog/invoices", headers=h, json={
        **base, "vendor_id": v1["id"],
    }).status_code == 409
    # …but a different vendor can reuse it.
    assert client.post("/api/v2/catalog/invoices", headers=h, json={
        **base, "vendor_id": v2["id"],
    }).status_code == 201


def test_update_item_costs_feedback(client, test_store_id):
    h = _admin(client, test_store_id)
    vendor = _mk_vendor(client, h)
    item = _mk_item(client, h, "222", "Chips", cost=0.80)
    resp = client.post("/api/v2/catalog/invoices", headers=h, json={
        "vendor_id": vendor["id"],
        "invoice_number": "INV-2",
        "invoice_date": "2026-08-21",
        "lines": [
            {"item_id": item["id"], "quantity": 12, "unit_cost": 0.95},
        ],
        "update_item_costs": True,
    })
    assert resp.status_code == 201, resp.text
    assert resp.json()["items_cost_updated"] == 1
    assert client.get(
        "/api/v2/catalog/items?q=222", headers=h,
    ).json()["rows"][0]["cost"] == 0.95


def test_invoice_update_status_and_lines(client, test_store_id):
    h = _admin(client, test_store_id)
    vendor = _mk_vendor(client, h)
    inv = client.post("/api/v2/catalog/invoices", headers=h, json={
        "vendor_id": vendor["id"],
        "invoice_number": "INV-3",
        "invoice_date": "2026-08-21",
        "subtotal": 100.0,
        "lines": [{"description": "Old line", "quantity": 1,
                   "unit_cost": 100.0}],
    }).json()["invoice"]

    # Mark paid.
    resp = client.put(
        f"/api/v2/catalog/invoices/{inv['id']}", headers=h,
        json={"status": "paid", "paid_on": "2026-08-25"},
    )
    assert resp.status_code == 200
    assert resp.json()["invoice"]["paid_on"] == "2026-08-25"

    # Reopen clears paid_on; lines replace-all.
    resp = client.put(
        f"/api/v2/catalog/invoices/{inv['id']}", headers=h,
        json={
            "status": "open",
            "lines": [
                {"description": "New line", "quantity": 2,
                 "unit_cost": 40.0},
            ],
        },
    )
    body = resp.json()["invoice"]
    assert body["paid_on"] is None
    assert [line["description"] for line in body["lines"]] == ["New line"]
    assert body["lines"][0]["line_total"] == 80.0


def test_invoice_list_filters_and_delete(client, test_store_id):
    h = _admin(client, test_store_id)
    v1 = _mk_vendor(client, h, "Vendor A")
    v2 = _mk_vendor(client, h, "Vendor B")
    for vendor, number, status in (
        (v1, "A-1", "open"), (v1, "A-2", "paid"), (v2, "B-9", "open"),
    ):
        assert client.post("/api/v2/catalog/invoices", headers=h, json={
            "vendor_id": vendor["id"], "invoice_number": number,
            "invoice_date": "2026-08-22", "status": status,
            "paid_on": "2026-08-22" if status == "paid" else None,
        }).status_code == 201

    body = client.get(
        f"/api/v2/catalog/invoices?vendor_id={v1['id']}", headers=h,
    ).json()
    assert body["total"] == 2
    assert set(body) == {"rows", "total", "page", "total_pages"}
    assert client.get(
        "/api/v2/catalog/invoices?status=paid", headers=h,
    ).json()["total"] == 1
    assert client.get(
        "/api/v2/catalog/invoices?q=B-", headers=h,
    ).json()["total"] == 1

    target = body["rows"][0]["id"]
    assert client.delete(
        f"/api/v2/catalog/invoices/{target}", headers=h,
    ).status_code == 200
    assert client.get(
        f"/api/v2/catalog/invoices/{target}", headers=h,
    ).status_code == 404


def test_employee_reads_but_cannot_manage_invoices(client, test_store_id):
    h = _admin(client, test_store_id)
    vendor = _mk_vendor(client, h)
    emp, etok = make_employee_client(test_store_id)
    eh = _headers(etok)
    assert emp.get(
        "/api/v2/catalog/invoices", headers=eh,
    ).status_code == 200
    assert emp.post("/api/v2/catalog/invoices", headers=eh, json={
        "vendor_id": vendor["id"], "invoice_number": "NOPE",
        "invoice_date": "2026-08-22",
    }).status_code == 403
