"""Operations batch reports — Returned Check Status, Bank Txn
Breakdown, Daily Drops, Check Deposits."""
from datetime import date, datetime, time


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


# ── Returned Check Status ────────────────────────────────────


def _make_returned_check(client, store_id, *, bounced_on, amount,
                          status="pending", recovered_amount=0.0,
                          customer_name="Customer"):
    """Create a ReturnCheck. If `recovered_amount` is non-zero, also
    create a ReturnCheckPayment installment so the property-based
    `recovered_total` reflects it."""
    from app import ReturnCheck, ReturnCheckPayment, db
    with client.application.app_context():
        rc = ReturnCheck(store_id=store_id, bounced_on=bounced_on,
                         customer_name=customer_name, amount=amount,
                         status=status)
        db.session.add(rc); db.session.commit()
        if recovered_amount:
            db.session.add(ReturnCheckPayment(
                return_check_id=rc.id, amount=recovered_amount,
                paid_on=bounced_on, payment_method="cash"))
            db.session.commit()
        return rc.id


def test_returned_check_status_buckets_per_status(client, test_store_id):
    _admin_login(client, test_store_id)
    today = date.today()
    _make_returned_check(client, test_store_id, bounced_on=today,
                          amount=100, status="pending")
    _make_returned_check(client, test_store_id, bounced_on=today,
                          amount=200, status="recovered",
                          recovered_amount=180)
    _make_returned_check(client, test_store_id, bounced_on=today,
                          amount=50, status="loss")
    _make_returned_check(client, test_store_id, bounced_on=today,
                          amount=30, status="fraud")
    resp = client.get("/reports/returned-check-status")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "Pending" in body
    assert "Recovered" in body
    assert "Loss" in body
    assert "Fraud" in body
    # Total Amount KPI = 100+200+50+30 = 380.
    assert "$380.00" in body
    # Recovered KPI = 180 (recovered_amount, not full amount).
    assert "$180.00" in body
    # Net G/L KPI = 180 - (50+30) = 100.
    assert "$100.00" in body


def test_returned_check_status_csv(client, test_store_id):
    _admin_login(client, test_store_id)
    today = date.today()
    _make_returned_check(client, test_store_id, bounced_on=today,
                          amount=200, status="recovered",
                          recovered_amount=200)
    resp = client.get("/reports/returned-check-status.csv")
    body = resp.get_data(as_text=True)
    assert "Status,Count,Amount,Recovered" in body
    assert "Recovered,1,200.00,200.00" in body
    assert "NET G/L,,,200.00" in body


# ── Bank Transactions Breakdown ──────────────────────────────


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
                    desc="Charge", category_slug="", txn_id="txn_x"):
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


def test_bank_txn_breakdown_groups_by_category(client, test_store_id):
    _admin_login(client, test_store_id)
    aid = _make_bank_account(client, test_store_id)
    today = datetime.combine(date.today(), time(9, 0))
    _make_bank_txn(client, test_store_id, aid, when=today,
                    amount_cents=-360, category_slug="bank_charge_230",
                    txn_id="bc1")
    _make_bank_txn(client, test_store_id, aid, when=today,
                    amount_cents=-150, category_slug="bank_charge_230",
                    txn_id="bc2")
    _make_bank_txn(client, test_store_id, aid, when=today,
                    amount_cents=20000, category_slug="",
                    txn_id="dep1")
    resp = client.get("/reports/bank-transactions-breakdown")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    # Grouping label includes the canonical bank-charge name.
    assert "Bank charge" in body  # "Bank charge — ••0230 (MSB)"
    # Inflow KPI = $200; Outflow = $5.10 (abs).
    assert "$200.00" in body
    assert "$5.10" in body
    # Net Flow = 200 - 5.10 = 194.90.
    assert "$194.90" in body


def test_bank_txn_breakdown_csv(client, test_store_id):
    _admin_login(client, test_store_id)
    aid = _make_bank_account(client, test_store_id)
    when = datetime.combine(date.today(), time(9, 0))
    _make_bank_txn(client, test_store_id, aid, when=when,
                    amount_cents=-100, category_slug="bank_charge_230",
                    txn_id="csv_bc")
    resp = client.get("/reports/bank-transactions-breakdown.csv")
    body = resp.get_data(as_text=True)
    assert "Category,Count,Signed Amount,Absolute Amount" in body


# ── Daily Drops ──────────────────────────────────────────────


def _make_daily_drop(client, store_id, *, report_date, amount,
                     drop_time=time(10, 0)):
    from app import DailyDrop, db
    with client.application.app_context():
        d = DailyDrop(store_id=store_id, report_date=report_date,
                      drop_time=drop_time, amount=amount)
        db.session.add(d); db.session.commit()
        return d.id


def test_daily_drops_aggregates_per_day(client, test_store_id):
    _admin_login(client, test_store_id)
    today = date.today()
    _make_daily_drop(client, test_store_id, report_date=today,
                      amount=100)
    _make_daily_drop(client, test_store_id, report_date=today,
                      amount=200)
    if today.day > 1:
        prior = today.replace(day=today.day - 1)
        _make_daily_drop(client, test_store_id, report_date=prior,
                          amount=50)
        expected_total = "$350.00"
        expected_days = "2 days"
    else:
        expected_total = "$300.00"
        expected_days = "1 day"
    resp = client.get("/reports/daily-drops")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "Total Dropped" in body
    assert expected_total in body
    assert expected_days in body
    assert today.strftime('%b %d') in body  # day card label


def test_daily_drops_csv(client, test_store_id):
    _admin_login(client, test_store_id)
    today = date.today()
    _make_daily_drop(client, test_store_id, report_date=today,
                      amount=125.50)
    resp = client.get("/reports/daily-drops.csv")
    body = resp.get_data(as_text=True)
    assert "Date,Drop Count,Total Dropped" in body
    assert f"{today.isoformat()},1,125.50" in body
    assert "TOTAL,1,125.50" in body


# ── Check Deposits ───────────────────────────────────────────


def _make_check_deposit(client, store_id, *, report_date, amount,
                         deposit_time=time(11, 0)):
    from app import CheckDeposit, db
    with client.application.app_context():
        cd = CheckDeposit(store_id=store_id, report_date=report_date,
                          deposit_time=deposit_time, amount=amount)
        db.session.add(cd); db.session.commit()
        return cd.id


def test_check_deposits_aggregates_per_day(client, test_store_id):
    _admin_login(client, test_store_id)
    today = date.today()
    _make_check_deposit(client, test_store_id, report_date=today,
                        amount=500)
    _make_check_deposit(client, test_store_id, report_date=today,
                        amount=250)
    resp = client.get("/reports/check-deposits")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "Total Deposited" in body
    assert "$750.00" in body
    assert "1 day" in body


def test_check_deposits_csv(client, test_store_id):
    _admin_login(client, test_store_id)
    today = date.today()
    _make_check_deposit(client, test_store_id, report_date=today,
                        amount=42.50)
    resp = client.get("/reports/check-deposits.csv")
    body = resp.get_data(as_text=True)
    assert "Date,Deposit Count,Total Deposited" in body
    assert f"{today.isoformat()},1,42.50" in body
    assert "TOTAL,1,42.50" in body


# ── Auth ─────────────────────────────────────────────────────


def test_operations_batch_routes_require_admin(client):
    for path in ("/reports/returned-check-status",
                 "/reports/bank-transactions-breakdown",
                 "/reports/daily-drops",
                 "/reports/check-deposits"):
        resp = client.get(path, follow_redirects=False)
        assert resp.status_code in (302, 303), path
        assert "/login" in resp.headers.get("Location", ""), path
