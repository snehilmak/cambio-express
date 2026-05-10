"""Audit batch reports — High-Value Transfers, Employee Activity,
Bank-Rule Audit Log, Cancelled Transfers."""
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


def _make_transfer(client, store_id, *, send_date, amount, fee=2.0,
                   federal_tax=0.0, country="MX", company="Intermex",
                   sender_name="S", recipient_name="R",
                   created_by=None, confirm="X", status="Sent",
                   status_notes=""):
    from app import Transfer, db
    with client.application.app_context():
        t = Transfer(
            store_id=store_id, send_date=send_date,
            sender_name=sender_name, recipient_name=recipient_name,
            country=country, confirm_number=confirm,
            company=company, send_amount=amount,
            fee=fee, federal_tax=federal_tax, status=status,
            status_notes=status_notes,
            created_by=created_by,
        )
        db.session.add(t); db.session.commit()
        return t.id


def _make_employee(client, store_id, *, username, full_name=""):
    from app import User, db
    with client.application.app_context():
        u = User(username=username, full_name=full_name,
                 role="employee", store_id=store_id)
        u.set_password("p")
        db.session.add(u); db.session.commit()
        return u.id


# ── High-Value Transfers ─────────────────────────────────────






def test_high_value_csv(client, test_store_id):
    _admin_login(client, test_store_id)
    today = date.today()
    _make_transfer(client, test_store_id, send_date=today,
                   amount=5000, sender_name="Whale",
                   recipient_name="Receiver", confirm="W1")
    resp = client.get("/reports/high-value-transfers.csv")
    body = resp.get_data(as_text=True)
    assert "Date,Sender,Recipient,Country,Company,Send Amount" in body
    assert "Whale,Receiver" in body
    assert "5000.00" in body


# ── Employee Activity ────────────────────────────────────────




def test_employee_activity_csv(client, test_store_id):
    _admin_login(client, test_store_id)
    eid = _make_employee(client, test_store_id, username="bob",
                          full_name="Bob")
    today = date.today()
    _make_transfer(client, test_store_id, send_date=today, amount=100,
                   created_by=eid, confirm="B1")
    resp = client.get("/reports/employee-activity.csv")
    body = resp.get_data(as_text=True)
    assert "Employee,Username,Active Transfers,Total Sent" in body
    assert "Bob,bob,1,100.00" in body


# ── Bank-Rule Audit Log ──────────────────────────────────────


def _make_bank_account(client, store_id, *, last4="0210", slug="fca_aud"):
    from app import StripeBankAccount, db
    with client.application.app_context():
        a = StripeBankAccount(store_id=store_id,
                              stripe_account_id=slug,
                              display_name="Acct", last4=last4,
                              currency="usd")
        db.session.add(a); db.session.commit()
        return a.id


def _make_bank_rule(client, store_id, *, target_kind="bank_charge_210",
                    desc_match_type="contains", desc_match_value="UTILITY"):
    from app import BankRule, db
    with client.application.app_context():
        r = BankRule(store_id=store_id, enabled=True,
                     desc_match_type=desc_match_type,
                     desc_match_value=desc_match_value,
                     target_kind=target_kind, auto_post=False)
        db.session.add(r); db.session.commit()
        return r.id


def _make_bank_txn(client, store_id, acct_id, *, when, amount_cents,
                    desc="", category_slug="", matched_rule_id=None,
                    txn_id="x"):
    from app import BankTransaction, db
    with client.application.app_context():
        t = BankTransaction(store_id=store_id,
                            stripe_bank_account_id=acct_id,
                            stripe_transaction_id=txn_id,
                            amount_cents=amount_cents, description=desc,
                            posted_at=when, status="posted",
                            category_slug=category_slug,
                            matched_rule_id=matched_rule_id)
        db.session.add(t); db.session.commit()
        return t.id




def test_bank_rule_audit_csv(client, test_store_id):
    _admin_login(client, test_store_id)
    aid = _make_bank_account(client, test_store_id)
    rid = _make_bank_rule(client, test_store_id,
                            desc_match_value="ELECTRIC")
    when = datetime.combine(date.today(), time(9, 0))
    _make_bank_txn(client, test_store_id, aid, when=when,
                    amount_cents=-200, matched_rule_id=rid,
                    desc="ELECTRIC", txn_id="csv_ar")
    resp = client.get("/reports/bank-rule-audit.csv")
    body = resp.get_data(as_text=True)
    assert "Rule,Match,Target,Matched Count,Total Amount" in body
    assert "ELECTRIC" in body


# ── Cancelled Transfers ──────────────────────────────────────




def test_cancelled_transfers_csv(client, test_store_id):
    _admin_login(client, test_store_id)
    today = date.today()
    _make_transfer(client, test_store_id, send_date=today, amount=150,
                   sender_name="Charlie", confirm="CC1",
                   status="Canceled", status_notes="reason")
    resp = client.get("/reports/cancelled-transfers.csv")
    body = resp.get_data(as_text=True)
    assert "Date,Sender,Recipient,Country,Company,Status" in body
    assert "Charlie" in body
    assert "Canceled" in body
    assert "reason" in body


# ── Auth ─────────────────────────────────────────────────────


def test_audit_batch_routes_require_admin(client):
    for path in ("/reports/high-value-transfers",
                 "/reports/employee-activity",
                 "/reports/bank-rule-audit",
                 "/reports/cancelled-transfers"):
        resp = client.get(path, follow_redirects=False)
        assert resp.status_code in (302, 303), path
        assert "/login" in resp.headers.get("Location", ""), path
