"""PosImport ingest flow (P1-9 PR2): preview, mapping, commit.

Synthetic NAXML fixtures only (see test_naxml). The invariants
under test:

  * preview parses a ZIP of journals, aggregates per (day,
    register), groups outside sales under "Pay at pump", and
    lists unmapped merchandise codes,
  * mapping CRUD validates department ownership,
  * commit is blocked (422) while any seen code is unmapped,
  * commit books the business day into DayClose with
    source="gilbarco" and re-running is idempotent (upsert),
  * bad payloads fail with 422, employees are denied (403).
"""
import base64
import io
import zipfile

from tests.Modules.PosImport.test_naxml import FUEL_SALE, REFUND, _sale
from tests.conftest import login_admin, make_employee_client


def _headers(token):
    return {"Authorization": f"Bearer {token}"}


def _admin(client, test_store_id):
    return _headers(login_admin(client, test_store_id))


def _zip_b64(*docs: str) -> str:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for i, doc in enumerate(docs):
            z.writestr(f"PJR{i:04}.xml", doc.encode("ISO-8859-1"))
    return base64.b64encode(buf.getvalue()).decode()


def _outside_fuel_sale() -> str:
    # FUEL_SALE with the pay-at-pump marker + synthetic register id.
    return (
        FUEL_SALE
        .replace("<RegisterID>2</RegisterID>",
                 "<RegisterID>10008</RegisterID>"
                 '<OutsideSalesFlag value="yes"/>')
    )


def _mk_department(client, h, name):
    resp = client.post("/api/v2/dayclose/departments", headers=h,
                       json={"name": name})
    assert resp.status_code == 201, resp.text
    return resp.json()["department"]


def _map_codes(client, h, mapping):
    resp = client.put("/api/v2/posimport/mapping", headers=h, json={
        "mappings": [
            {"merchandise_code": code, "department_id": dept_id}
            for code, dept_id in mapping.items()
        ],
    })
    assert resp.status_code == 200, resp.text
    return resp.json()["mappings"]


PAYLOAD_DOCS = (
    _sale(),                                   # reg 1 grocery-ish, 2.99 cash
    _sale(merch="4", amount="5.00", tax_collected="0.41",
          tender_code="creditCards", tendered="5.41", change="0"),
    REFUND,                                    # reg 1, −20 cash, code 17
)


def test_preview_aggregates_and_flags_unmapped(client, test_store_id):
    h = _admin(client, test_store_id)
    body = {"content_base64": _zip_b64(*PAYLOAD_DOCS, _outside_fuel_sale())}
    resp = client.post("/api/v2/posimport/naxml/preview", headers=h, json=body)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["file_count"] == 4
    assert data["event_count"] == 4
    assert data["business_dates"] == ["2024-10-14"]
    labels = [r["register_label"] for r in data["registers"]]
    assert labels == ["Register 1", "Pay at pump"]
    reg1, pump = data["registers"]
    assert pump["net_sales"] == 30.0
    assert pump["fuel"][0]["gallons"] == 11.198
    assert reg1["net_sales"] == 2.99 + 5.00 - 20.00
    assert reg1["refunds"] == 20.0
    # Nothing mapped yet — every seen code is flagged.
    assert set(data["unmapped_codes"]) == {"17", "4", "1024"}


def test_mapping_rejects_foreign_department(client, test_store_id):
    h = _admin(client, test_store_id)
    resp = client.put("/api/v2/posimport/mapping", headers=h, json={
        "mappings": [{"merchandise_code": "4", "department_id": 99999}],
    })
    assert resp.status_code == 404


def test_commit_blocks_until_mapped_then_books_day(client, test_store_id):
    h = _admin(client, test_store_id)
    body = {
        "content_base64": _zip_b64(*PAYLOAD_DOCS, _outside_fuel_sale()),
        "day": "2024-10-14",
    }
    # Unmapped codes → 422 naming them.
    resp = client.post("/api/v2/posimport/naxml/commit", headers=h, json=body)
    assert resp.status_code == 422
    assert "1024" in resp.json()["detail"]

    groc = _mk_department(client, h, "Grocery")
    misc = _mk_department(client, h, "Misc")
    fuel = _mk_department(client, h, "Fuel")
    rows = _map_codes(client, h, {
        "17": misc["id"], "4": groc["id"], "1024": fuel["id"],
    })
    assert len(rows) == 3

    resp = client.post("/api/v2/posimport/naxml/commit", headers=h, json=body)
    assert resp.status_code == 200, resp.text
    result = resp.json()
    assert result["closes_written"] == 2
    assert sorted(result["registers"]) == ["Pay at pump", "Register 1"]

    day = client.get(
        "/api/v2/dayclose/day/2024-10-14", headers=h,
    ).json()
    assert len(day["closes"]) == 2
    by_label = {c["register_label"]: c for c in day["closes"]}
    assert by_label["Pay at pump"]["source"] == "gilbarco"
    assert by_label["Pay at pump"]["gross_sales"] == 30.0
    assert by_label["Register 1"]["gross_sales"] == -12.01
    assert by_label["Register 1"]["cash_total"] == -16.76
    assert by_label["Register 1"]["card_total"] == 5.41
    # Departments: refund pushed Misc negative → dropped; Grocery
    # and Fuel carry their sales.
    totals = {
        t["department_name"]: t["amount"]
        for t in day["department_totals"]
    }
    assert totals == {"Grocery": 5.0, "Fuel": 30.0}

    # Re-committing replaces (upsert) instead of stacking.
    resp = client.post("/api/v2/posimport/naxml/commit", headers=h, json=body)
    assert resp.status_code == 200
    day = client.get(
        "/api/v2/dayclose/day/2024-10-14", headers=h,
    ).json()
    assert len(day["closes"]) == 2


def test_commit_wrong_day_and_bad_payloads(client, test_store_id):
    h = _admin(client, test_store_id)
    resp = client.post("/api/v2/posimport/naxml/commit", headers=h, json={
        "content_base64": _zip_b64(_sale()), "day": "2020-01-01",
    })
    assert resp.status_code == 422
    assert "no activity" in resp.json()["detail"]
    resp = client.post("/api/v2/posimport/naxml/preview", headers=h, json={
        "content_base64": "!!!not-base64!!!",
    })
    assert resp.status_code == 422
    resp = client.post("/api/v2/posimport/naxml/preview", headers=h, json={
        "content_base64": base64.b64encode(b"hello world").decode(),
    })
    assert resp.status_code == 422


def test_employee_denied(client, test_store_id):
    emp_client, emp_jwt = make_employee_client(test_store_id)
    resp = client.post(
        "/api/v2/posimport/naxml/preview", headers=_headers(emp_jwt),
        json={"content_base64": _zip_b64(_sale())},
    )
    assert resp.status_code == 403
