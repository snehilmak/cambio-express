"""Gilbarco NAXML-POSJournal parser (P1-9 PR1).

Fixtures are SYNTHETIC, modeled on the real Passport 22.01
structure (NAXML-POSJournal 3.4) — no production journal data in
the repo. The invariants under test:

  * sale parse: items, merchandise codes, taxes, tenders, change,
    summary totals, BusinessDate,
  * fuel lines carry grade + gallons and aggregate per grade,
  * refunds are negative end-to-end and net out of the day,
  * cancelled lines (and thus void events) contribute nothing,
  * register-open events capture the drawer float,
  * aggregation groups by (business date, register),
  * tender bucketing: cash vs card networks vs other,
  * malformed / non-POSJournal / XXE input fails loudly.
"""
import pytest

from api.Modules.PosImport.Services import (
    PosJournalParseError,
    aggregate_events,
    parse_pjr,
)


def _doc(event_xml: str) -> str:
    return f"""<?xml version ="1.0" encoding="ISO-8859-1" standalone="no"?>
 <NAXML-POSJournal version="3.4" release="3.4.0">
  <TransmissionHeader>
   <StoreLocationID>1</StoreLocationID>
   <VendorName>Gilbarco-VeederRoot</VendorName>
  </TransmissionHeader>
  <JournalReport>
   <JournalHeader>
    <ReportSequenceNumber>1274</ReportSequenceNumber>
    <PrimaryReportPeriod>2</PrimaryReportPeriod>
    <BeginDate>2024-10-13</BeginDate>
   </JournalHeader>
   {event_xml}
  </JournalReport>
 </NAXML-POSJournal>"""


def _sale(business_date="2024-10-14", register="1", merch="17",
          amount="2.99", tax_collected="0.25", tender_code="cash",
          tendered="4.00", change="-0.76", event_dt=None):
    # event_dt: optional ISO timestamp -> <EventDateTime> (G-3).
    dt_el = (
        f"<EventDateTime>{event_dt}</EventDateTime>" if event_dt else ""
    )
    return _doc(f"""<SaleEvent>
    {dt_el}
    <CashierID>91</CashierID>
    <RegisterID>{register}</RegisterID>
    <TillID>1310</TillID>
    <TransactionID>1472</TransactionID>
    <BusinessDate>{business_date}</BusinessDate>
    <TransactionDetailGroup>
     <TransactionLine status="normal">
      <ItemLine>
       <ItemCode><POSCode>2</POSCode></ItemCode>
       <Description>7lb ice bag</Description>
       <ActualSalesPrice>{amount}</ActualSalesPrice>
       <MerchandiseCode>{merch}</MerchandiseCode>
       <SalesQuantity>1</SalesQuantity>
       <SalesAmount>{amount}</SalesAmount>
      </ItemLine>
     </TransactionLine>
     <TransactionLine status="normal">
      <TransactionTax>
       <TaxLevelID>99</TaxLevelID>
       <TaxableSalesAmount>{amount}</TaxableSalesAmount>
       <TaxCollectedAmount>{tax_collected}</TaxCollectedAmount>
      </TransactionTax>
     </TransactionLine>
     <TransactionLine status="normal">
      <TenderInfo>
       <Tender>
        <TenderCode>{tender_code}</TenderCode>
        <TenderSubCode>generic</TenderSubCode>
       </Tender>
       <TenderAmount>{tendered}</TenderAmount>
       <ChangeFlag value="no"/>
      </TenderInfo>
     </TransactionLine>
     <TransactionLine status="normal">
      <TenderInfo>
       <Tender>
        <TenderCode>cash</TenderCode>
        <TenderSubCode>generic</TenderSubCode>
       </Tender>
       <TenderAmount>{change}</TenderAmount>
       <ChangeFlag value="yes"/>
      </TenderInfo>
     </TransactionLine>
    </TransactionDetailGroup>
    <TransactionSummary>
     <TransactionTotalGrossAmount>{amount}</TransactionTotalGrossAmount>
     <TransactionTotalNetAmount>{amount}</TransactionTotalNetAmount>
     <TransactionTotalTaxNetAmount>{tax_collected}</TransactionTotalTaxNetAmount>
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
       <ActualSalesPrice>2.679</ActualSalesPrice>
       <MerchandiseCode>1024</MerchandiseCode>
       <SalesQuantity>11.198</SalesQuantity>
       <SalesAmount>30</SalesAmount>
      </FuelLine>
     </TransactionLine>
     <TransactionLine status="normal">
      <TenderInfo>
       <Tender>
        <TenderCode>outsideCredit</TenderCode>
        <TenderSubCode>generic</TenderSubCode>
       </Tender>
       <TenderAmount>30</TenderAmount>
       <ChangeFlag value="no"/>
      </TenderInfo>
     </TransactionLine>
    </TransactionDetailGroup>
    <TransactionSummary>
     <TransactionTotalGrossAmount>30</TransactionTotalGrossAmount>
     <TransactionTotalNetAmount>30</TransactionTotalNetAmount>
     <TransactionTotalTaxNetAmount>0</TransactionTotalTaxNetAmount>
    </TransactionSummary>
   </SaleEvent>""")


REFUND = _doc("""<RefundEvent>
    <CashierID>91</CashierID>
    <RegisterID>1</RegisterID>
    <TransactionID>3585</TransactionID>
    <BusinessDate>2024-10-14</BusinessDate>
    <TransactionDetailGroup>
     <TransactionLine status="normal">
      <ItemLine>
       <Description>lotto payout reversal</Description>
       <MerchandiseCode>17</MerchandiseCode>
       <SalesQuantity>-1</SalesQuantity>
       <SalesAmount>-20</SalesAmount>
      </ItemLine>
     </TransactionLine>
     <TransactionLine status="normal">
      <TenderInfo>
       <Tender>
        <TenderCode>cash</TenderCode>
        <TenderSubCode>generic</TenderSubCode>
       </Tender>
       <TenderAmount>-20</TenderAmount>
       <ChangeFlag value="yes"/>
      </TenderInfo>
     </TransactionLine>
    </TransactionDetailGroup>
    <TransactionSummary>
     <TransactionTotalGrossAmount>-20</TransactionTotalGrossAmount>
     <TransactionTotalNetAmount>-20</TransactionTotalNetAmount>
     <TransactionTotalTaxNetAmount>0</TransactionTotalTaxNetAmount>
    </TransactionSummary>
   </RefundEvent>""")


VOID = _doc("""<VoidEvent>
    <CashierID>91</CashierID>
    <RegisterID>1</RegisterID>
    <TransactionID>1877</TransactionID>
    <BusinessDate>2024-10-14</BusinessDate>
    <TransactionDetailGroup>
     <TransactionLine status="cancel">
      <ItemLine>
       <Description>voided item</Description>
       <MerchandiseCode>4</MerchandiseCode>
       <SalesQuantity>1</SalesQuantity>
       <SalesAmount>5.49</SalesAmount>
      </ItemLine>
     </TransactionLine>
    </TransactionDetailGroup>
   </VoidEvent>""")


REGISTER_OPEN = _doc("""<OtherEvent>
    <CashierID>91</CashierID>
    <RegisterID>1</RegisterID>
    <TransactionID>4035</TransactionID>
    <BusinessDate>2024-10-14</BusinessDate>
    <RegisterDetail detailType="open">
     <CashInDrawer>500</CashInDrawer>
     <TenderSource>open</TenderSource>
    </RegisterDetail>
   </OtherEvent>""")


# ── Parsing ────────────────────────────────────────────────


def test_parse_sale_event():
    ev = parse_pjr(_sale())
    assert ev.kind == "sale"
    assert ev.business_date.isoformat() == "2024-10-14"
    assert ev.register_id == "1"
    assert [i.merchandise_code for i in ev.items] == ["17"]
    assert ev.items[0].amount_cents == 299
    assert ev.gross_cents == 299
    assert ev.tax_cents == 25
    # Tender 4.00 + change −0.76 = 3.24 net cash.
    assert sum(t.amount_cents for t in ev.tenders) == 324
    assert [t.is_change for t in ev.tenders] == [False, True]


def test_parse_fuel_sale():
    ev = parse_pjr(FUEL_SALE)
    line = ev.items[0]
    assert line.is_fuel is True
    assert line.fuel_grade_id == "001"
    assert line.gallons == pytest.approx(11.198)
    assert line.amount_cents == 3000
    assert line.merchandise_code == "1024"


def test_parse_refund_is_negative():
    ev = parse_pjr(REFUND)
    assert ev.kind == "refund"
    assert ev.net_cents == -2000
    assert ev.items[0].amount_cents == -2000


def test_void_event_has_no_countable_lines():
    ev = parse_pjr(VOID)
    assert ev.kind == "void"
    assert ev.items == []
    assert ev.tenders == []


def test_register_open_captures_drawer_float():
    ev = parse_pjr(REGISTER_OPEN)
    assert ev.kind == "other"
    assert ev.opening_cash_cents == 50000


def test_rejects_garbage_and_wrong_documents():
    with pytest.raises(PosJournalParseError):
        parse_pjr("this is not xml")
    with pytest.raises(PosJournalParseError):
        parse_pjr("<NAXML-MovementReport></NAXML-MovementReport>")
    with pytest.raises(PosJournalParseError):
        parse_pjr(_doc("<JournalNote>nothing here</JournalNote>"))


def test_rejects_entity_expansion_attack():
    evil = """<?xml version="1.0"?>
<!DOCTYPE bomb [<!ENTITY a "aaaa"><!ENTITY b "&a;&a;&a;&a;">]>
<NAXML-POSJournal><JournalReport><SaleEvent>
<RegisterID>&b;</RegisterID>
</SaleEvent></JournalReport></NAXML-POSJournal>"""
    with pytest.raises(PosJournalParseError):
        parse_pjr(evil)


# ── Aggregation ────────────────────────────────────────────


def test_day_aggregation_shapes_a_register_close():
    events = [
        parse_pjr(_sale()),                          # reg 1: 2.99 + .25 tax
        parse_pjr(_sale(merch="4", amount="5.00",
                        tax_collected="0.41",
                        tender_code="creditCards",
                        tendered="5.41", change="0")),  # reg 1, card
        parse_pjr(FUEL_SALE),                        # reg 2: fuel 30
        parse_pjr(REFUND),                           # reg 1: −20 cash
        parse_pjr(VOID),                             # nothing
        parse_pjr(REGISTER_OPEN),                    # reg 1 float 500
    ]
    days = aggregate_events(events)
    assert [(a.business_date.isoformat(), a.register_id) for a in days] == [
        ("2024-10-14", "1"), ("2024-10-14", "2"),
    ]
    reg1, reg2 = days
    # 2.99 + 5.00 − 20.00 refund = −12.01 net merchandise.
    assert reg1.net_sales_cents == -1201
    assert reg1.refunds_cents == 2000
    assert reg1.tax_cents == 25 + 41
    assert reg1.sale_count == 2
    assert reg1.refund_count == 1
    assert reg1.opening_cash_cents == 50000
    # Cash: 4.00 − 0.76 change − 20.00 refund = −16.76.
    assert reg1.cash_cents == -1676
    assert reg1.card_cents == 541
    assert reg1.departments == {"17": 299 - 2000, "4": 500}

    assert reg2.net_sales_cents == 3000
    assert reg2.card_cents == 3000
    assert reg2.departments == {"1024": 3000}
    assert reg2.fuel["001"].gallons == pytest.approx(11.198)
    assert reg2.fuel["001"].amount_cents == 3000
    assert reg2.fuel["001"].description == "UNLEAD REG"


def test_aggregation_ignores_undated_events():
    ev = parse_pjr(_sale())
    ev.business_date = None
    assert aggregate_events([ev]) == []
