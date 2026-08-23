"""Price-book warm start from staged Gilbarco journals (P2-3).

Fixtures are SYNTHETIC, modeled on the real Passport 22.01
structure — no production journal data in the repo. The invariants
under test:

  * parser captures POSCode + format + RegularSellPrice per item,
  * harvest dedupes by scan code with newest-sale-wins pricing,
  * fuel lines and code-less items never become price-book rows,
  * merchandise codes map to departments via PosMerchandiseMap,
  * seeding skips codes already in the price book (operator edits
    survive) and is idempotent,
  * the commit needs catalog.update — cashiers can't seed.
"""
from tests._app import db, db_session
from tests.conftest import login_admin, make_employee_client


def _headers(token):
    return {"Authorization": f"Bearer {token}"}


def _admin(client, test_store_id):
    return _headers(login_admin(client, test_store_id))


def _doc(event_xml: str) -> str:
    return f"""<?xml version ="1.0" encoding="ISO-8859-1" standalone="no"?>
 <NAXML-POSJournal version="3.4" release="3.4.0">
  <TransmissionHeader>
   <StoreLocationID>1</StoreLocationID>
   <VendorName>Gilbarco-VeederRoot</VendorName>
  </TransmissionHeader>
  <JournalReport>
   {event_xml}
  </JournalReport>
 </NAXML-POSJournal>"""


def _sale(business_date, *, pos_code, fmt="upc", desc, merch="400",
          price="2.99", txn="1000"):
    return _doc(f"""<SaleEvent>
    <CashierID>91</CashierID>
    <RegisterID>1</RegisterID>
    <TransactionID>{txn}</TransactionID>
    <BusinessDate>{business_date}</BusinessDate>
    <TransactionDetailGroup>
     <TransactionLine status="normal">
      <ItemLine>
       <ItemCode>
        <POSCodeFormat format="{fmt}"></POSCodeFormat>
        <POSCode>{pos_code}</POSCode>
       </ItemCode>
       <Description>{desc}</Description>
       <ActualSalesPrice>{price}</ActualSalesPrice>
       <MerchandiseCode>{merch}</MerchandiseCode>
       <RegularSellPrice>{price}</RegularSellPrice>
       <SalesQuantity>1</SalesQuantity>
       <SalesAmount>{price}</SalesAmount>
      </ItemLine>
     </TransactionLine>
    </TransactionDetailGroup>
    <TransactionSummary>
     <TransactionTotalGrossAmount>{price}</TransactionTotalGrossAmount>
     <TransactionTotalNetAmount>{price}</TransactionTotalNetAmount>
     <TransactionTotalTaxNetAmount>0</TransactionTotalTaxNetAmount>
    </TransactionSummary>
   </SaleEvent>""")


FUEL_SALE = _doc("""<SaleEvent>
    <CashierID>91</CashierID>
    <RegisterID>2</RegisterID>
    <TransactionID>900</TransactionID>
    <BusinessDate>2024-10-14</BusinessDate>
    <TransactionDetailGroup>
     <TransactionLine status="normal">
      <FuelLine>
       <FuelGradeID>001</FuelGradeID>
       <FuelPositionID>9</FuelPositionID>
       <Description>UNLEAD REG</Description>
       <MerchandiseCode>1024</MerchandiseCode>
       <SalesQuantity>11.198</SalesQuantity>
       <SalesAmount>30</SalesAmount>
      </FuelLine>
     </TransactionLine>
    </TransactionDetailGroup>
   </SaleEvent>""")


def _stage(store_id, filename, xml):
    from api.Modules.PosImport.Services import stage_journal_file
    with db_session():
        stage_journal_file(
            db.session, store_id,
            filename=filename, content=xml.encode("ISO-8859-1"),
        )
        db.session.commit()


def test_parser_captures_pos_code_and_regular_price():
    from api.Modules.PosImport.Services import parse_pjr
    event = parse_pjr(_sale(
        "2024-10-14", pos_code="049000012345", desc="Cola 20oz",
        price="3.19",
    ))
    [item] = event.items
    assert item.pos_code == "049000012345"
    assert item.pos_code_format == "upc"
    assert item.regular_price_cents == 319


def test_harvest_newest_price_wins_and_maps_departments(
    client, test_store_id,
):
    h = _admin(client, test_store_id)
    # Same item sold on two days with a price change + a rename.
    _stage(test_store_id, "PJR1.xml", _sale(
        "2024-10-10", pos_code="111", fmt="plu", desc="ice bag",
        merch="17", price="2.49", txn="1",
    ))
    _stage(test_store_id, "PJR2.xml", _sale(
        "2024-10-14", pos_code="111", fmt="plu", desc="7lb ice bag",
        merch="17", price="2.99", txn="2",
    ))
    # A fuel-only file contributes nothing.
    _stage(test_store_id, "PJR3.xml", FUEL_SALE)

    # Map merchandise code 17 → a department.
    dept = client.post("/api/v2/dayclose/departments", headers=h, json={
        "name": "Ice",
    }).json()["department"]
    resp = client.put("/api/v2/posimport/mapping", headers=h, json={
        "mappings": [
            {"merchandise_code": "17", "department_id": dept["id"]},
        ],
    })
    assert resp.status_code == 200

    body = client.get(
        "/api/v2/posimport/pricebook/preview", headers=h,
    ).json()
    assert body["new_count"] == 1
    assert body["existing_count"] == 0
    [row] = body["items"]
    assert row["pos_code"] == "111"
    assert row["pos_code_format"] == "plu"
    assert row["description"] == "7lb ice bag"   # newest wins
    assert row["price"] == 2.99                  # newest wins
    assert row["seen_count"] == 2
    assert row["department_id"] == dept["id"]
    assert row["department_name"] == "Ice"


def test_seed_skips_existing_and_is_idempotent(client, test_store_id):
    h = _admin(client, test_store_id)
    _stage(test_store_id, "PJRA.xml", _sale(
        "2024-10-14", pos_code="049000012345", desc="Cola 20oz",
        price="3.19", txn="10",
    ))
    _stage(test_store_id, "PJRB.xml", _sale(
        "2024-10-14", pos_code="222", fmt="plu", desc="Fountain drink",
        price="1.29", txn="11",
    ))
    # The operator already keyed the cola by hand — seeding must
    # not touch it.
    resp = client.post("/api/v2/catalog/items", headers=h, json={
        "pos_code": "049000012345", "name": "Cola (hand-entered)",
        "price": 3.49,
    })
    assert resp.status_code == 201

    body = client.post(
        "/api/v2/posimport/pricebook/commit", headers=h,
    ).json()
    assert body == {"created": 1, "skipped_existing": 1}

    items = client.get(
        "/api/v2/catalog/items?q=fountain", headers=h,
    ).json()
    [seeded] = items["rows"]
    assert seeded["name"] == "Fountain drink"
    assert seeded["price"] == 1.29
    assert seeded["source"] == "gilbarco"

    # Hand-entered row untouched.
    cola = client.get(
        "/api/v2/catalog/items?q=049000012345", headers=h,
    ).json()["rows"][0]
    assert cola["name"] == "Cola (hand-entered)"
    assert cola["price"] == 3.49
    assert cola["source"] == "manual"

    # Second run creates nothing.
    again = client.post(
        "/api/v2/posimport/pricebook/commit", headers=h,
    ).json()
    assert again["created"] == 0
    assert again["skipped_existing"] == 2


def test_seed_requires_catalog_update(client, test_store_id):
    emp, etok = make_employee_client(test_store_id)
    eh = _headers(etok)
    assert emp.get(
        "/api/v2/posimport/pricebook/preview", headers=eh,
    ).status_code == 403
    assert emp.post(
        "/api/v2/posimport/pricebook/commit", headers=eh,
    ).status_code == 403
