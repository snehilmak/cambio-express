"""Tests for the Daily Book's auto-derived Money Transfer receipts line.

The spreadsheet treats the "Money Transfer" entry in the Receipts section as
a subtotal of the per-company MT table below. We mirror that by:

- Rendering the daily_report's money_transfer input as readonly.
- On save, recomputing money_transfer = sum of MT rows (amount + fees + tax
  + commission) and ignoring whatever the client submitted for that field.
"""
from datetime import date
from app import app as flask_app, db


def _store_id():
    from app import Store
    with flask_app.app_context():
        return Store.query.filter_by(slug="test-store").first().id


def _save_daily_report(logged_in_client, ds, form):
    return logged_in_client.post(f"/daily/{ds}", data=form, follow_redirects=False)


def _base_form(money_transfer="9999.00"):
    """All the daily_report fields, mostly zeroed. Callers override the
    money-transfer line to prove the server ignores it."""
    zero_fields = [
        "taxable_sales", "non_taxable", "sales_tax", "bill_payment_charge",
        "phone_recargas", "boost_mobile", "money_order",
        "check_cashing_fees", "return_check_hold_fees", "return_check_paid_back",
        "forward_balance", "from_bank", "other_cash_in", "rebates_commissions",
        "cash_purchases", "cash_expense", "check_purchases", "check_expense",
        "outside_cash_drops", "cash_deposit", "checks_deposit", "safe_balance",
        "payroll_expense", "other_cash_out", "over_short",
    ]
    form = {k: "0" for k in zero_fields}
    form["notes"] = ""
    form["money_transfer"] = money_transfer
    return form


def test_daily_report_renders_money_transfer_readonly(logged_in_client):
    ds = date.today().isoformat()
    resp = logged_in_client.get(f"/daily/{ds}")
    assert resp.status_code == 200
    html = resp.data.decode("utf-8", errors="ignore")
    # Find the money_transfer input and confirm `readonly` is nearby.
    idx = html.find('name="money_transfer"')
    assert idx != -1, "money_transfer input missing"
    assert "readonly" in html[max(0, idx - 200):idx + 200]
    # The "Auto" badge should be next to the label.
    assert 'class="auto-badge">Auto' in html


def test_daily_report_ignores_submitted_money_transfer(logged_in_client):
    sid = _store_id()
    ds = date.today().isoformat()
    # Submit with a bogus $9,999 money_transfer and no MT rows — the server
    # should recompute it as 0.00 because the MT table is empty.
    form = _base_form(money_transfer="9999.00")
    _save_daily_report(logged_in_client, ds, form)
    from app import DailyReport
    with flask_app.app_context():
        r = DailyReport.query.filter_by(
            store_id=sid,
            report_date=date.fromisoformat(ds)).first()
        assert r is not None
        # Zero — the submitted $9,999 is discarded; recomputed from empty MT table.
        assert abs(r.money_transfer) < 0.01


def test_daily_report_derives_money_transfer_from_mt_rows(logged_in_client):
    sid = _store_id()
    ds = date.today().isoformat()
    form = _base_form(money_transfer="0")
    # Intermex: 500 amount + 5 fees + 5 tax + 0 commission = 510.
    # Maxi:    200 amount + 2 fees + 2 tax + 0 commission = 204.
    # Barri:   100 amount + 1 fees + 1 tax + 0 commission = 102.
    # Grand total = 816.00.
    form.update({
        "mt_amount_intermex": "500.00", "mt_fees_intermex": "5.00",
        "mt_tax_intermex": "5.00",       "mt_commission_intermex": "0.00",
        "mt_amount_maxi":     "200.00", "mt_fees_maxi":     "2.00",
        "mt_tax_maxi":         "2.00",   "mt_commission_maxi": "0.00",
        "mt_amount_barri":    "100.00", "mt_fees_barri":    "1.00",
        "mt_tax_barri":        "1.00",   "mt_commission_barri": "0.00",
    })
    _save_daily_report(logged_in_client, ds, form)
    from app import DailyReport, MoneyTransferSummary
    with flask_app.app_context():
        r = DailyReport.query.filter_by(
            store_id=sid,
            report_date=date.fromisoformat(ds)).first()
        assert r is not None
        # Server-computed from MT inputs.
        assert abs(r.money_transfer - 816.00) < 0.01
        # MT summary rows persisted correctly too.
        rows = {x.company: x for x in MoneyTransferSummary.query.filter_by(
            store_id=sid, report_date=date.fromisoformat(ds)).all()}
        assert abs(rows["Intermex"].amount - 500.00) < 0.01
        assert abs(rows["Maxi"].amount - 200.00) < 0.01


def test_daily_report_money_transfer_updates_when_mt_rows_change(logged_in_client):
    """Editing the MT rows on a subsequent save refreshes the derived total."""
    sid = _store_id()
    ds = date.today().isoformat()
    # First save: $510 total (Intermex only).
    form = _base_form()
    form.update({
        "mt_amount_intermex": "500.00", "mt_fees_intermex": "5.00",
        "mt_tax_intermex": "5.00", "mt_commission_intermex": "0.00",
    })
    _save_daily_report(logged_in_client, ds, form)
    # Second save: bump to $1000 amount → new total should be 1010.
    form.update({
        "mt_amount_intermex": "1000.00",
    })
    _save_daily_report(logged_in_client, ds, form)
    from app import DailyReport
    with flask_app.app_context():
        r = DailyReport.query.filter_by(
            store_id=sid,
            report_date=date.fromisoformat(ds)).first()
        assert abs(r.money_transfer - 1010.00) < 0.01
