"""Unit tests for the Intermex daily-close report parser.

The fixture below is SYNTHETIC — a hand-authored report in the Intermex
layout with fake agency + amounts. No real customer/settlement data
lives in the repo; the parser is exercised against representative
structure (three sections, cancelled `*` + replacement `R` markers,
the number-glued-to-cashier quirk in the Giros column).
"""
from datetime import date

import pytest

from api.Modules.ReportImport.Services import (
    ReportParseError,
    parse_intermex_text,
)


# Mirrors the real layout: jumbled multi-line column headers, Giros
# rows with the cashier glued to the balance, a cancelled (*) and a
# replacement (R) row, and each section's stated footer totals. The
# Giros deposit total ($321.00) EXCLUDES the cancelled row (55.50).
SAMPLE = """\
Agencia: 9999 TEST AGENCY LLC (TX-0000)
Creado el: 01/03/2026 09:30 AM
Reporte de cierre del día
Fecha: 01/02/2026
Total a depositar Pagos en efectivo
$421.00 $421.00
Las transacciones canceladas y anuladas se marcan con (*)
Giro de reemplazo será marcado con (R)
Transacciones Monto a depositar
Giros $321.00
Money order $300.30
Pago Facturas $100.00
Giros
Total: 3 Procesados: 2 Anulados: 1
Cancelados: 0 Cancelados pendientes de reembolso: 0
Monto Cargo BalanceCreado
Giro # Imp.
envío s transac.por
1001 100.00 10.00 1.00 111.00TESTER
1002* 50.00 5.00 0.50 55.50TESTER
1003R 200.00 8.00 2.00 210.00TESTER
Monto Total cargos Balance transac.
$300.00 $18.00 $321.00
Money order
Total: 1 Procesados: 1 Anulados: 0
BalanceCreado
MO # Monto Cargo
transac.por
5001 300.00 2.00 300.30 TESTER
Monto Total cargos Balance transac.
$300.00 $2.00 $300.30
Pago Facturas
Total: 1 Procesados: 1 Cancelados(C): 0
Monto BalanceCreado
Pago # Cargo
factura transac.por
20 96.50 3.50 100.00 TESTER
Monto Total cargos Balance transac.
$96.50 $3.50 $100.00
"""


def test_header_parsed():
    r = parse_intermex_text(SAMPLE)
    assert r.agency == "9999 TEST AGENCY LLC (TX-0000)"
    assert r.report_date == date(2026, 1, 2)


def test_giros_rows_and_money_math():
    r = parse_intermex_text(SAMPLE)
    assert len(r.giros) == 3
    g = r.giros[0]
    assert g.confirm_number == "1001"
    # Maps onto Transfer: send + fee + federal_tax == total_collected.
    assert (g.send_amount, g.fee, g.federal_tax, g.total_collected) == (
        100.0, 10.0, 1.0, 111.0,
    )
    assert g.cashier == "TESTER"
    assert all(x.reconciles for x in r.giros)


def test_cancelled_and_replacement_markers():
    r = parse_intermex_text(SAMPLE)
    by_num = {g.confirm_number: g for g in r.giros}
    assert by_num["1002"].cancelled is True
    assert by_num["1002"].replacement is False
    assert by_num["1003"].replacement is True
    assert by_num["1003"].cancelled is False
    # active_giros drops the cancelled one.
    assert [g.confirm_number for g in r.active_giros] == ["1001", "1003"]


def test_section_totals_and_reconciliation():
    r = parse_intermex_text(SAMPLE)
    assert r.giros_totals is not None
    assert r.giros_totals.count == 3
    assert r.giros_totals.voided == 1
    assert r.giros_totals.balance == 321.0
    # Active giros (excl. cancelled) sum to the stated deposit total.
    assert round(sum(g.total_collected for g in r.active_giros), 2) == 321.0
    assert r.all_reconcile is True


def test_money_order_and_bill_payment_sections():
    r = parse_intermex_text(SAMPLE)
    assert len(r.money_orders) == 1
    mo = r.money_orders[0]
    assert mo.confirm_number == "5001"
    assert mo.send_amount == 300.0 and mo.fee == 2.0
    assert mo.federal_tax == 0.0  # no per-row tax outside Giros
    assert r.money_order_totals.balance == 300.3

    assert len(r.bill_payments) == 1
    assert r.bill_payments[0].total_collected == 100.0


def test_rejects_non_intermex_text():
    with pytest.raises(ReportParseError):
        parse_intermex_text("just some random text\nwith no agencia header")


def test_rejects_report_with_no_rows():
    with pytest.raises(ReportParseError):
        parse_intermex_text(
            "Agencia: 1 X\nFecha: 01/02/2026\nno transactions here\n"
        )
