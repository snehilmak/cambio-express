"""Financial batch reports — Period P&L, ACH Volume, Bank Charges
by Account, Period Comparison, Fees vs. Federal Tax."""
from datetime import date, datetime, time, timedelta


def _admin_login(client, store_id):
    from app import User, Store, db
    with client.application.app_context():
        u = User.query.filter_by(store_id=store_id, role="admin").first()
        uid = u.id
        s = db.session.get(Store, store_id)
        s.plan = "pro"
        s.billing_cycle = "monthly"
        db.session.commit()
    with client.session_transaction() as sess:
        sess["user_id"] = uid
        sess["role"] = "admin"
        sess["store_id"] = store_id


def _make_daily_report(client, store_id, *, report_date,
                        taxable_sales=0.0, non_taxable=0.0,
                        bill_payment_charge=0.0, phone_recargas=0.0,
                        boost_mobile=0.0, check_cashing_fees=0.0,
                        return_check_hold_fees=0.0,
                        rebates_commissions=0.0,
                        cash_purchases=0.0, check_purchases=0.0,
                        cash_expense=0.0, check_expense=0.0,
                        payroll_expense=0.0):
    from app import DailyReport, db
    with client.application.app_context():
        r = DailyReport(store_id=store_id, report_date=report_date,
                        taxable_sales=taxable_sales,
                        non_taxable=non_taxable,
                        bill_payment_charge=bill_payment_charge,
                        phone_recargas=phone_recargas,
                        boost_mobile=boost_mobile,
                        check_cashing_fees=check_cashing_fees,
                        return_check_hold_fees=return_check_hold_fees,
                        rebates_commissions=rebates_commissions,
                        cash_purchases=cash_purchases,
                        check_purchases=check_purchases,
                        cash_expense=cash_expense,
                        check_expense=check_expense,
                        payroll_expense=payroll_expense)
        db.session.add(r); db.session.commit()
        return r.id


def _make_transfer(client, store_id, *, send_date, amount, fee=0.0,
                   federal_tax=0.0, company="Intermex",
                   confirm="X", status="Sent"):
    from app import Transfer, db
    with client.application.app_context():
        t = Transfer(
            store_id=store_id, send_date=send_date,
            sender_name="S", recipient_name="R",
            country="MX", confirm_number=confirm,
            company=company, send_amount=amount,
            fee=fee, federal_tax=federal_tax, status=status,
        )
        db.session.add(t); db.session.commit()
        return t.id


def _make_ach_batch(client, store_id, *, ach_date, ach_amount,
                    company="Intermex", batch_ref="REF1"):
    from app import ACHBatch, db
    with client.application.app_context():
        b = ACHBatch(store_id=store_id, ach_date=ach_date,
                     company=company, batch_ref=batch_ref,
                     ach_amount=ach_amount)
        db.session.add(b); db.session.commit()
        return b.id


# ── Period P&L ───────────────────────────────────────────────


def test_period_pl_aggregates_daily_report_lines(client, test_store_id):
    _admin_login(client, test_store_id)
    today = date.today()
    _make_daily_report(client, test_store_id, report_date=today,
                       taxable_sales=300, non_taxable=100,
                       cash_expense=80, payroll_expense=120)
    _make_transfer(client, test_store_id, send_date=today, amount=200,
                   fee=5.0, confirm="T1")
    resp = client.get("/reports/period-pl")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    # Income: taxable + non-taxable + transfer fee = 300+100+5 = 405.
    assert "$405.00" in body
    # Expenses: cash_expense + payroll = 80+120 = 200.
    assert "$200.00" in body
    # Net: 405 - 200 = 205.
    assert "$205.00" in body


def test_period_pl_csv(client, test_store_id):
    _admin_login(client, test_store_id)
    today = date.today()
    _make_daily_report(client, test_store_id, report_date=today,
                       taxable_sales=100)
    resp = client.get("/reports/period-pl.csv")
    body = resp.get_data(as_text=True)
    assert "Section,Line,Amount" in body
    assert "Income,Taxable Sales,100.00" in body
    assert ",Total Income,100.00" in body


# ── ACH Volume ───────────────────────────────────────────────




def test_ach_volume_csv(client, test_store_id):
    _admin_login(client, test_store_id)
    today = date.today()
    _make_ach_batch(client, test_store_id, ach_date=today,
                     ach_amount=1000, batch_ref="CSV1")
    resp = client.get("/reports/ach-volume.csv")
    body = resp.get_data(as_text=True)
    assert "Company,Batch Count,Total ACH" in body
    assert "Intermex,1,1000.00" in body
    assert "TOTAL,1,1000.00" in body


# ── Bank Charges by Account ──────────────────────────────────


def _make_bank_account(client, store_id, *, last4="0210", slug="fca_x"):
    from app import StripeBankAccount, db
    with client.application.app_context():
        a = StripeBankAccount(store_id=store_id,
                              stripe_account_id=slug,
                              display_name="Acct", last4=last4,
                              currency="usd")
        db.session.add(a); db.session.commit()
        return a.id


def _make_bank_txn(client, store_id, acct_id, *, when, amount_cents,
                    desc="Charge", category_slug="bank_charge_210",
                    txn_id="x"):
    from app import BankTransaction, db
    with client.application.app_context():
        t = BankTransaction(store_id=store_id,
                            stripe_bank_account_id=acct_id,
                            stripe_transaction_id=txn_id,
                            amount_cents=amount_cents, description=desc,
                            posted_at=when, status="posted",
                            category_slug=category_slug)
        db.session.add(t); db.session.commit()
        return t.id


def test_bank_charges_by_account_groups_by_account(client, test_store_id):
    _admin_login(client, test_store_id)
    a210 = _make_bank_account(client, test_store_id, last4="0210",
                                slug="fca_210")
    a230 = _make_bank_account(client, test_store_id, last4="0230",
                                slug="fca_230")
    when = datetime.combine(date.today(), time(9, 0))
    _make_bank_txn(client, test_store_id, a210, when=when,
                    amount_cents=-500, category_slug="bank_charge_210",
                    txn_id="bc210_1")
    _make_bank_txn(client, test_store_id, a210, when=when,
                    amount_cents=-300, category_slug="bank_charge_210",
                    txn_id="bc210_2")
    _make_bank_txn(client, test_store_id, a230, when=when,
                    amount_cents=-1000, category_slug="bank_charge_230",
                    txn_id="bc230_1")
    # Non-bank-charge txn should not appear.
    _make_bank_txn(client, test_store_id, a210, when=when,
                    amount_cents=-200, category_slug="ignore",
                    txn_id="ign1")
    resp = client.get("/reports/bank-charges-by-account")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "0210" in body
    assert "0230" in body
    # Total Charges KPI = 5+3+10 = 18.00.
    assert "$18.00" in body
    # 0230 alone = 10.00.
    assert "$10.00" in body
    # Non-bank-charge ($2.00) not included.
    assert "$2.00" not in body


def test_bank_charges_by_account_csv(client, test_store_id):
    _admin_login(client, test_store_id)
    aid = _make_bank_account(client, test_store_id, last4="0210")
    when = datetime.combine(date.today(), time(9, 0))
    _make_bank_txn(client, test_store_id, aid, when=when,
                    amount_cents=-100, category_slug="bank_charge_210",
                    txn_id="csv_bc")
    resp = client.get("/reports/bank-charges-by-account.csv")
    body = resp.get_data(as_text=True)
    assert "Account,Last 4,Charge Count,Total Charges,Avg / Charge" in body
    assert "0210" in body


# ── Period Comparison ────────────────────────────────────────


def test_period_comparison_compares_to_prior_period(client, test_store_id):
    _admin_login(client, test_store_id)
    # Current period: May 1-31. Prior: April 1-30.
    _make_transfer(client, test_store_id, send_date=date(2026, 5, 5),
                   amount=300, fee=10, confirm="C1")
    _make_transfer(client, test_store_id, send_date=date(2026, 4, 10),
                   amount=200, fee=5, confirm="P1")
    resp = client.get("/reports/period-comparison?from=2026-05-01&to=2026-05-31")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    # Both period labels appear (current = May, prior = same-length
    # window ending the day before — Mar 31 – Apr 30 for May 1-31).
    assert "May 01" in body
    assert "Apr 30" in body
    # Each metric row.
    assert "Transfers" in body
    assert "Total Sent" in body
    assert "Net Income" in body


def test_period_comparison_csv(client, test_store_id):
    _admin_login(client, test_store_id)
    _make_transfer(client, test_store_id, send_date=date(2026, 5, 5),
                   amount=100, fee=2, confirm="C1")
    resp = client.get("/reports/period-comparison.csv?from=2026-05-01&to=2026-05-31")
    body = resp.get_data(as_text=True)
    assert "Metric" in body
    assert "Transfers" in body
    assert "Net Income" in body


# ── Fees vs. Federal Tax ─────────────────────────────────────




def test_fees_vs_tax_csv(client, test_store_id):
    _admin_login(client, test_store_id)
    today = date.today()
    _make_transfer(client, test_store_id, send_date=today, amount=100,
                   fee=2.0, federal_tax=1.0, confirm="F1")
    resp = client.get("/reports/fees-vs-tax.csv")
    body = resp.get_data(as_text=True)
    assert "Line,Amount" in body
    assert "Fees (store revenue),2.00" in body
    assert "Federal Tax (pass-through),1.00" in body
    assert "Tax / Fee Ratio" in body


# ── Auth ─────────────────────────────────────────────────────


def test_financial_batch_routes_require_admin(client):
    for path in ("/reports/period-pl",
                 "/reports/ach-volume",
                 "/reports/bank-charges-by-account",
                 "/reports/period-comparison",
                 "/reports/fees-vs-tax"):
        resp = client.get(path, follow_redirects=False)
        assert resp.status_code in (302, 303), path
        assert "/login" in resp.headers.get("Location", ""), path
