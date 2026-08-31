"""Register activity on the dashboard (D-4).

The tiles a manager scans for trouble — receipt count, voided
tickets, refunds, fuel — plus the latest-receipts panel.

The rule under test is the same one that runs through every POS
total in this codebase: a cancelled line is visible but never
counted. Here that means a voided pump sale must not move the
fuel-gallons figure.
"""
from datetime import date, datetime

import pytest

from api.Modules.PosImport.Models import PosTransaction, PosTransactionLine
from tests._app import db, db_session
from tests.conftest import login_admin

DAY = date(2025, 12, 8)


def _set_type(test_store_id, business_type="cstore"):
    """The register blocks gate on module_day_close, which the
    c-store bundle turns on."""
    from api.Modules.Tenancy.Models import Store
    with db_session():
        db.session.get(Store, test_store_id).business_type = business_type
        db.session.commit()


def _headers(token):
    return {"Authorization": f"Bearer {token}"}


def _txn(store_id, *, source_file, no, cents, kind="sale", voided=False):
    txn = PosTransaction(
        store_id=store_id, business_date=DAY, source_file=source_file,
        kind=kind, register_id="1", cashier_id="3", transaction_no=no,
        receipt_at=datetime(2025, 12, 8, 13, 31, 38),
        gross_cents=cents, net_cents=cents, tax_cents=0,
        grand_total_cents=cents, has_voided_line=voided,
    )
    db.session.add(txn)
    db.session.flush()
    return txn


def _fuel_line(txn, *, gallons, cents, status="normal"):
    db.session.add(PosTransactionLine(
        transaction_id=txn.id, store_id=txn.store_id, business_date=DAY,
        line_seq=1, status=status, description="UNLEADED",
        quantity=1.0, amount_cents=cents, is_fuel=True,
        fuel_grade_id="1", fuel_position="4", gallons=gallons,
    ))


def _summary(client, test_store_id):
    resp = client.get(
        "/api/v2/dashboard/summary",
        headers=_headers(login_admin(client, test_store_id)),
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_block_is_absent_until_a_day_is_booked(client, test_store_id):
    """A store that keys its book by hand must not be shown an
    empty '0 receipts' panel — that reads as a broken register."""
    _set_type(test_store_id)
    body = _summary(client, test_store_id)
    assert body["register"] is None
    assert body["recent_receipts"] == []


def test_counts_receipts_voids_and_refunds(client, test_store_id):
    _set_type(test_store_id)
    with db_session():
        _txn(test_store_id, source_file="A.xml", no="1", cents=300)
        _txn(test_store_id, source_file="B.xml", no="2", cents=1200,
             voided=True)
        _txn(test_store_id, source_file="C.xml", no="3", cents=-500,
             kind="refund")
        db.session.commit()

    reg = _summary(client, test_store_id)["register"]
    assert reg is not None
    assert reg["date"] == DAY.isoformat()
    assert reg["receipts"] == 3
    assert reg["voided_tickets"] == 1
    assert reg["refunds"] == 1
    # 3.00 + 12.00 − 5.00
    assert reg["total_rung"] == pytest.approx(10.00)


def test_voided_fuel_line_does_not_move_gallons(client, test_store_id):
    """The trap: a voided pump sale did not put fuel in a car."""
    _set_type(test_store_id)
    with db_session():
        real = _txn(test_store_id, source_file="A.xml", no="1", cents=4000)
        _fuel_line(real, gallons=10.0, cents=4000)
        killed = _txn(
            test_store_id, source_file="B.xml", no="2", cents=0,
            voided=True,
        )
        _fuel_line(killed, gallons=999.0, cents=400000, status="cancel")
        db.session.commit()

    reg = _summary(client, test_store_id)["register"]
    assert reg["fuel_gallons"] == pytest.approx(10.0), (
        "a cancelled pump line must not move fuel"
    )
    assert reg["fuel_sales"] == pytest.approx(40.00)


def test_recent_receipts_are_newest_first_and_flag_voids(
    client, test_store_id,
):
    _set_type(test_store_id)
    with db_session():
        _txn(test_store_id, source_file="A.xml", no="1", cents=300)
        _txn(test_store_id, source_file="B.xml", no="2", cents=1200,
             voided=True)
        db.session.commit()

    receipts = _summary(client, test_store_id)["recent_receipts"]
    assert len(receipts) == 2
    # Same receipt_at, so the id tiebreak decides — newest first.
    assert receipts[0]["transaction_no"] == "2"
    assert receipts[0]["has_voided_line"] is True
    assert receipts[1]["has_voided_line"] is False
    assert receipts[0]["total"] == pytest.approx(12.00)


def test_falls_back_to_the_latest_booked_day(client, test_store_id):
    """Nothing is booked for today at 8am; the block should show
    the last real day rather than nothing."""
    _set_type(test_store_id)
    with db_session():
        _txn(test_store_id, source_file="A.xml", no="1", cents=300)
        db.session.commit()

    reg = _summary(client, test_store_id)["register"]
    assert reg["date"] == DAY.isoformat()
    assert reg["is_today"] is (DAY == date.today())


def test_another_stores_tickets_never_leak(client, test_store_id):
    _set_type(test_store_id)
    from api.Modules.Tenancy.Models import Store

    with db_session():
        _txn(test_store_id, source_file="A.xml", no="mine", cents=300)
        other = Store(
            name="Other", slug="other-dash-store",
            email="other-dash@x.com", plan="basic",
        )
        db.session.add(other)
        db.session.commit()
        _txn(other.id, source_file="X.xml", no="theirs", cents=99999)
        db.session.commit()

    body = _summary(client, test_store_id)
    assert body["register"]["receipts"] == 1
    assert {r["transaction_no"] for r in body["recent_receipts"]} == {"mine"}
