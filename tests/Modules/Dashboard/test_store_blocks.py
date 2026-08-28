"""Generic store dashboard blocks (D-1, Cronysoft-style).

The summary gains three store-generic blocks:
  * ``sales``     — RegisterClose rollups (today/yesterday/MTD/
                    d7/d15/d30) + a zero-filled 14-day trend.
                    Present only with module_day_close.
  * ``purchases`` — PurchaseInvoice rollups + open-invoice count.
                    Present only with module_price_book.
  * ``clocked_in``— open TimeClockEntry rows joined to the roster.
                    Universal (the time clock isn't module-gated).
"""
from datetime import date, timedelta

from tests._app import db, db_session
from tests.conftest import login_admin


def _headers(token):
    return {"Authorization": f"Bearer {token}"}


def _set_type(test_store_id, business_type):
    from api.Modules.Tenancy.Models import Store
    with db_session():
        db.session.get(Store, test_store_id).business_type = business_type
        db.session.commit()


def _summary(client, token):
    resp = client.get(
        "/api/v2/dashboard/summary", headers=_headers(token),
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def _seed_register_close(store_id, day, cents):
    from api.Modules.DayClose.Models import RegisterClose
    with db_session():
        db.session.add(RegisterClose(
            store_id=store_id, report_date=day,
            register_label="Register 1", shift_label="",
            gross_sales_cents=cents,
        ))
        db.session.commit()


def test_sales_block_rollups_and_trend(client, test_store_id):
    _set_type(test_store_id, "cstore")
    today = date.today()
    _seed_register_close(test_store_id, today, 9_936_14)
    _seed_register_close(test_store_id, today - timedelta(days=1), 10_676_01)
    _seed_register_close(test_store_id, today - timedelta(days=10), 5_000_00)
    # Outside every window except d30.
    _seed_register_close(test_store_id, today - timedelta(days=20), 1_000_00)

    token = login_admin(client, test_store_id)
    sales = _summary(client, token)["sales"]
    assert sales is not None
    assert sales["today"] == 9936.14
    assert sales["yesterday"] == 10676.01
    assert sales["d7"] == 9936.14 + 10676.01
    assert sales["d15"] == 9936.14 + 10676.01 + 5000.00
    assert sales["d30"] == 9936.14 + 10676.01 + 5000.00 + 1000.00
    # Trend: 14 zero-filled days, oldest first, today last.
    assert len(sales["trend"]) == 14
    assert sales["trend"][-1] == {
        "date": today.isoformat(), "amount": 9936.14,
    }
    assert sales["trend"][0]["amount"] == 0.0


def test_purchases_block_and_open_invoices(client, test_store_id):
    _set_type(test_store_id, "cstore")
    today = date.today()
    from api.Modules.Catalog.Models import PurchaseInvoice, Vendor
    with db_session():
        v = Vendor(store_id=test_store_id, name="Core-Mark")
        db.session.add(v)
        db.session.flush()
        db.session.add(PurchaseInvoice(
            store_id=test_store_id, vendor_id=v.id,
            invoice_number="INV-1", invoice_date=today,
            subtotal_cents=3_000_00, tax_cents=300_00,
            other_cents=79_43, status="open",
        ))
        db.session.add(PurchaseInvoice(
            store_id=test_store_id, vendor_id=v.id,
            invoice_number="INV-2",
            invoice_date=today - timedelta(days=10),
            subtotal_cents=1_000_00, status="paid",
            paid_on=today,
        ))
        db.session.commit()

    token = login_admin(client, test_store_id)
    purchases = _summary(client, token)["purchases"]
    assert purchases is not None
    assert purchases["today"] == 3379.43
    assert purchases["d7"] == 3379.43
    assert purchases["d15"] == 3379.43 + 1000.00
    assert purchases["open_count"] == 1
    assert purchases["open_total"] == 3379.43


def test_clocked_in_lists_open_shifts_only(client, test_store_id):
    _set_type(test_store_id, "cstore")
    from datetime import datetime
    from api.Modules.Tenancy.Models import StoreEmployee
    from api.Modules.TimeClock.Models import TimeClockEntry
    with db_session():
        on = StoreEmployee(store_id=test_store_id, name="Dora Lazo")
        off = StoreEmployee(store_id=test_store_id, name="Sam Off")
        db.session.add_all([on, off])
        db.session.flush()
        db.session.add(TimeClockEntry(
            store_id=test_store_id, store_employee_id=on.id,
            clock_in_at=datetime.utcnow(),
        ))
        db.session.add(TimeClockEntry(
            store_id=test_store_id, store_employee_id=off.id,
            clock_in_at=datetime.utcnow(),
            clock_out_at=datetime.utcnow(),
        ))
        db.session.commit()

    token = login_admin(client, test_store_id)
    clocked = _summary(client, token)["clocked_in"]
    assert [r["name"] for r in clocked] == ["Dora Lazo"]
    assert clocked[0]["clock_in_at"]


def test_msb_hybrid_gets_no_retail_blocks(client, test_store_id):
    """Pre-pivot stores (msb_hybrid) have day_close/price_book off:
    no sales/purchases blocks, money-services payload intact."""
    _set_type(test_store_id, "msb_hybrid")
    token = login_admin(client, test_store_id)
    data = _summary(client, token)
    assert data["sales"] is None
    assert data["purchases"] is None
    assert isinstance(data["clocked_in"], list)
    assert "module_money_services" in data["modules"]
