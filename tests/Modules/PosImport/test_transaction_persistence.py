"""Persisted POS transactions (G-5).

Operators need to open a single transaction and see what sold on
it — including the lines the register voided mid-sale. Those lines
are now parsed and stored, which makes the load-bearing question
"does a stored void ever reach a money total?". It must not.
"""
from datetime import date

import pytest

from api.Modules.PosImport.Services import (
    LINE_STATUS_CANCEL, LINE_STATUS_NORMAL,
    aggregate_events, parse_pjr, rebuild_transactions,
)
from tests._app import db, db_session


def _doc(event_xml: str) -> str:
    return f"""<?xml version ="1.0" encoding="ISO-8859-1" standalone="no"?>
 <NAXML-POSJournal version="3.4" release="3.4.0">
  <TransmissionHeader><StoreLocationID>1</StoreLocationID></TransmissionHeader>
  <JournalReport>
   <JournalHeader><BeginTime>13:30:45</BeginTime></JournalHeader>
   {event_xml}
  </JournalReport>
 </NAXML-POSJournal>"""


# A sale where the cashier scanned a $50 item, voided it, then rang
# a $3 item. Only the $3 is money; the $50 must remain VISIBLE.
SALE_WITH_VOIDED_ITEM = _doc("""<SaleEvent>
    <EventSequenceID>7</EventSequenceID>
    <CashierID>3</CashierID>
    <RegisterID>1</RegisterID>
    <TillID>0318</TillID>
    <TransactionID>8945</TransactionID>
    <EventStartDate>2025-12-09</EventStartDate>
    <EventStartTime>13:30:45</EventStartTime>
    <ReceiptDate>2025-12-09</ReceiptDate>
    <ReceiptTime>13:31:38</ReceiptTime>
    <BusinessDate>2025-12-08</BusinessDate>
    <TrainingModeFlag value="no"/>
    <OutsideSalesFlag value="no"/>
    <TransactionDetailGroup>
     <TransactionLine status="cancel">
      <ItemLine>
       <ItemCode><POSCode>111111111111</POSCode></ItemCode>
       <Description>VOIDED PREMIUM ITEM</Description>
       <MerchandiseCode>10</MerchandiseCode>
       <SalesQuantity>1</SalesQuantity>
       <SalesAmount>50.00</SalesAmount>
      </ItemLine>
     </TransactionLine>
     <TransactionLine status="normal">
      <ItemLine>
       <ItemCode><POSCode>222222222222</POSCode>
        <POSCodeFormat format="upcA"></POSCodeFormat></ItemCode>
       <Description>CANDY BAR</Description>
       <EntryMethod method="scan"></EntryMethod>
       <ActualSalesPrice>3.00</ActualSalesPrice>
       <MerchandiseCode>10</MerchandiseCode>
       <SalesQuantity>1</SalesQuantity>
       <SalesAmount>3.00</SalesAmount>
       <ItemTax><TaxLevelID>101</TaxLevelID></ItemTax>
      </ItemLine>
     </TransactionLine>
     <TransactionLine status="normal">
      <TenderInfo>
       <Tender><TenderCode>cash</TenderCode>
        <TenderSubCode>generic</TenderSubCode></Tender>
       <TenderAmount>3.00</TenderAmount>
       <ChangeFlag value="no"/>
      </TenderInfo>
     </TransactionLine>
    </TransactionDetailGroup>
    <TransactionSummary>
     <TransactionTotalGrossAmount>3.00</TransactionTotalGrossAmount>
     <TransactionTotalNetAmount>3.00</TransactionTotalNetAmount>
     <TransactionTotalTaxNetAmount>0</TransactionTotalTaxNetAmount>
     <TransactionTotalGrandAmount direction="Collected">3.00</TransactionTotalGrandAmount>
    </TransactionSummary>
   </SaleEvent>""")

DAY = date(2025, 12, 8)


# ── The invariant ───────────────────────────────────────────


def test_voided_line_is_parsed_but_never_counted():
    """The whole risk of G-5 in one test: the voided $50 is
    readable, and the day still sees only $3."""
    ev = parse_pjr(SALE_WITH_VOIDED_ITEM)
    assert len(ev.items) == 2, "the voided line must not vanish"
    voided = [i for i in ev.items if i.status == LINE_STATUS_CANCEL]
    assert len(voided) == 1
    assert voided[0].amount_cents == 5000
    assert voided[0].description == "VOIDED PREMIUM ITEM"

    agg = aggregate_events([ev])[0]
    # $3 only — the $50 void contributes nothing.
    assert agg.departments == {"10": 300}
    assert agg.cash_cents == 300


def test_item_movement_excludes_voided_lines():
    """rebuild_item_day_sales sums `items` too — it documented that
    cancelled lines could never appear there, which G-5 made false.
    Selling and voking one unit must move zero units."""
    from api.Modules.PosImport.Services.ingest import rebuild_item_day_sales
    from api.Modules.PosImport.Models import PosItemDaySale
    from api.Modules.Tenancy.Models import Store

    with db_session():
        s = Store(name="Void Store", slug="void-item-store",
                  email="void@x.com", plan="basic")
        db.session.add(s); db.session.commit()
        ev = parse_pjr(SALE_WITH_VOIDED_ITEM)
        rebuild_item_day_sales(db.session, s.id, DAY, [ev])
        db.session.commit()

        rows = {
            r.pos_code: r for r in
            db.session.query(PosItemDaySale).filter_by(store_id=s.id).all()
        }
        assert "222222222222" in rows, "the real sale should move"
        assert rows["222222222222"].amount_cents == 300
        assert "111111111111" not in rows, (
            "a voided scan must not move inventory"
        )


# ── Persistence ─────────────────────────────────────────────


def _store(slug):
    from api.Modules.Tenancy.Models import Store
    s = Store(name=slug, slug=slug, email=f"{slug}@x.com", plan="basic")
    db.session.add(s); db.session.commit()
    return s.id


def test_transaction_and_lines_are_persisted():
    from api.Modules.PosImport.Models import (
        PosTransaction, PosTransactionLine, PosTransactionTender,
    )
    with db_session():
        sid = _store("txn-persist")
        ev = parse_pjr(SALE_WITH_VOIDED_ITEM)
        ev.source_file = "PJR340251209133139277539.xml"
        assert rebuild_transactions(db.session, sid, DAY, [ev]) == 1
        db.session.commit()

        txn = db.session.query(PosTransaction).filter_by(store_id=sid).one()
        assert txn.kind == "sale"
        assert txn.register_id == "1"
        assert txn.cashier_id == "3"
        assert txn.till_id == "0318"
        assert txn.transaction_no == "8945"
        assert txn.event_sequence_id == "7"
        assert txn.net_cents == 300
        assert txn.grand_total_cents == 300
        assert txn.receipt_at is not None
        assert txn.started_at is not None
        # The flag that lets the list mark a ticket without a join.
        assert txn.has_voided_line is True

        lines = (
            db.session.query(PosTransactionLine)
            .filter_by(transaction_id=txn.id)
            .order_by(PosTransactionLine.line_seq)
            .all()
        )
        assert len(lines) == 2
        assert lines[0].status == LINE_STATUS_CANCEL
        assert lines[0].description == "VOIDED PREMIUM ITEM"
        assert lines[1].status == LINE_STATUS_NORMAL
        assert lines[1].pos_code == "222222222222"
        assert lines[1].entry_method == "scan"
        assert lines[1].tax_level_id == "101"
        assert lines[1].amount_cents == 300

        tenders = (
            db.session.query(PosTransactionTender)
            .filter_by(transaction_id=txn.id).all()
        )
        assert len(tenders) == 1
        assert tenders[0].code == "cash"
        assert tenders[0].amount_cents == 300


def test_recommit_replaces_rather_than_duplicates():
    """Rebuilds are delete-and-replace, like the hourly buckets and
    item movement — re-committing a day must not double it."""
    from api.Modules.PosImport.Models import (
        PosTransaction, PosTransactionLine,
    )
    with db_session():
        sid = _store("txn-recommit")
        ev = parse_pjr(SALE_WITH_VOIDED_ITEM)
        ev.source_file = "PJR-one.xml"
        rebuild_transactions(db.session, sid, DAY, [ev])
        db.session.commit()
        rebuild_transactions(db.session, sid, DAY, [ev])
        db.session.commit()

        assert db.session.query(PosTransaction).filter_by(
            store_id=sid,
        ).count() == 1
        # Children replaced too — no orphans left behind.
        assert db.session.query(PosTransactionLine).filter_by(
            store_id=sid,
        ).count() == 2


def test_event_without_a_source_file_is_skipped():
    """No filename means no idempotence key, so storing it would
    duplicate on the next commit."""
    from api.Modules.PosImport.Models import PosTransaction
    with db_session():
        sid = _store("txn-nofile")
        ev = parse_pjr(SALE_WITH_VOIDED_ITEM)  # source_file left blank
        assert rebuild_transactions(db.session, sid, DAY, [ev]) == 0
        db.session.commit()
        assert db.session.query(PosTransaction).filter_by(
            store_id=sid,
        ).count() == 0


def test_other_days_are_untouched_by_a_rebuild():
    """Rebuilding one day must not clear another day's rows."""
    from api.Modules.PosImport.Models import PosTransaction
    other = date(2025, 12, 7)
    with db_session():
        sid = _store("txn-daysafe")
        ev = parse_pjr(SALE_WITH_VOIDED_ITEM)
        ev.source_file = "PJR-day8.xml"
        rebuild_transactions(db.session, sid, DAY, [ev])

        ev7 = parse_pjr(SALE_WITH_VOIDED_ITEM)
        ev7.business_date = other
        ev7.source_file = "PJR-day7.xml"
        rebuild_transactions(db.session, sid, other, [ev7])
        db.session.commit()

        # Rebuilding day 8 again leaves day 7 alone.
        rebuild_transactions(db.session, sid, DAY, [ev])
        db.session.commit()
        assert db.session.query(PosTransaction).filter_by(
            store_id=sid, business_date=other,
        ).count() == 1


# ── Real vendor file ────────────────────────────────────────


REAL_PJR = _doc("""<SaleEvent>
    <CashierID>3</CashierID><RegisterID>1</RegisterID>
    <TransactionID>8945</TransactionID>
    <BusinessDate>2025-12-08</BusinessDate>
    <TransactionDetailGroup>
     <TransactionLine status="normal">
      <ItemLine>
       <ItemCode><POSCode>852895003006</POSCode>
        <POSCodeFormat format="upcA"></POSCodeFormat>
        <POSCodeModifier name="pc">1</POSCodeModifier></ItemCode>
       <Description>ABW FIRE EAGLE 612oz CN</Description>
       <EntryMethod method="scan"></EntryMethod>
       <ActualSalesPrice>11.99</ActualSalesPrice>
       <MerchandiseCode>10</MerchandiseCode>
       <SellingUnits>1</SellingUnits>
       <RegularSellPrice>11.99</RegularSellPrice>
       <SalesQuantity>1</SalesQuantity>
       <SalesAmount>11.99</SalesAmount>
       <ItemTax><TaxLevelID>101</TaxLevelID></ItemTax>
      </ItemLine>
     </TransactionLine>
    </TransactionDetailGroup>
    <TransactionSummary>
     <TransactionTotalGrossAmount>28.98</TransactionTotalGrossAmount>
     <TransactionTotalNetAmount>31.37</TransactionTotalNetAmount>
     <TransactionTotalTaxNetAmount>2.39</TransactionTotalTaxNetAmount>
    </TransactionSummary>
   </SaleEvent>""")


def test_parses_the_shape_a_real_passport_file_uses():
    """Mirrors a genuine Passport 23.01 SaleEvent — the fields the
    viewer renders must all survive the round trip."""
    ev = parse_pjr(REAL_PJR)
    line = ev.items[0]
    assert line.pos_code == "852895003006"
    assert line.pos_code_format == "upcA"
    assert line.description == "ABW FIRE EAGLE 612oz CN"
    assert line.entry_method == "scan"
    assert line.selling_units == "1"
    assert line.actual_price_cents == 1199
    assert line.regular_price_cents == 1199
    assert line.tax_level_id == "101"
    assert ev.gross_cents == 2898
    assert ev.net_cents == 3137
    assert ev.tax_cents == 239
