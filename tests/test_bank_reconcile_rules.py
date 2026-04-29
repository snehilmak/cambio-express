"""Tests for Phase 3 bank reconcile + rules flow.

Stripe is never called — we exercise rule matching, manual
categorization, and the routes against in-memory rows.
"""
from datetime import datetime, timedelta


def _admin_login(client, store_id, *, plan="pro"):
    from app import User, Store, db
    with client.application.app_context():
        u = User.query.filter_by(store_id=store_id, role="admin").first()
        uid = u.id
        s = db.session.get(Store, store_id)
        s.plan = plan
        s.billing_cycle = "monthly"
        if plan == "trial":
            # Active trial — trial_ends_at in the future.
            s.trial_ends_at = datetime.utcnow() + timedelta(days=5)
        db.session.commit()
    with client.session_transaction() as s:
        s["user_id"] = uid
        s["role"] = "admin"
        s["store_id"] = store_id
    return client


def _make_account(app, store_id, *, slug="fca_t1", display="Checking", last4="1234"):
    from app import StripeBankAccount, db
    with app.app_context():
        a = StripeBankAccount(
            store_id=store_id, stripe_account_id=slug,
            display_name=display, last4=last4, currency="usd",
        )
        db.session.add(a); db.session.commit()
        return a.id


def _make_txn(app, store_id, acct_id, *, amount_cents, desc="MAXISEND CO ENTRY",
              when=None, txn_id="fctxn_1"):
    from app import BankTransaction, db
    with app.app_context():
        t = BankTransaction(
            store_id=store_id, stripe_bank_account_id=acct_id,
            stripe_transaction_id=txn_id,
            amount_cents=amount_cents, description=desc,
            posted_at=when or datetime.utcnow(), status="posted",
        )
        db.session.add(t); db.session.commit()
        return t.id


# ── pro_required gate ────────────────────────────────────────


def test_basic_plan_cannot_access_bank(client, test_store_id):
    _admin_login(client, test_store_id, plan="basic")
    resp = client.get("/bank", follow_redirects=False)
    assert resp.status_code == 302
    assert "/subscribe" in resp.headers["Location"]


def test_active_trial_can_access_bank(client, test_store_id):
    _admin_login(client, test_store_id, plan="trial")
    resp = client.get("/bank")
    assert resp.status_code == 200


def test_expired_trial_cannot_access_bank(client, test_store_id):
    from app import Store, db
    _admin_login(client, test_store_id, plan="trial")
    # Backdate so trial is expired.
    with client.application.app_context():
        s = db.session.get(Store, test_store_id)
        s.trial_ends_at = datetime.utcnow() - timedelta(days=10)
        s.grace_ends_at = datetime.utcnow() - timedelta(days=8)
        db.session.commit()
    resp = client.get("/bank", follow_redirects=False)
    assert resp.status_code == 302
    assert "/subscribe" in resp.headers["Location"]


def test_pro_plan_can_access_bank(client, test_store_id):
    _admin_login(client, test_store_id, plan="pro")
    resp = client.get("/bank")
    assert resp.status_code == 200


# ── _bank_rule_matches ───────────────────────────────────────


def test_rule_matches_description_contains(client, test_store_id):
    """contains is case-insensitive."""
    from app import BankRule, _bank_rule_matches
    _admin_login(client, test_store_id)
    app = client.application
    acct = _make_account(app, test_store_id)
    tid = _make_txn(app, test_store_id, acct, amount_cents=-18000,
                    desc="ACH/EmagineNet Inc")
    with app.app_context():
        from app import BankTransaction, db
        t = db.session.get(BankTransaction, tid)
        rule = BankRule(store_id=test_store_id, target_kind="check_expense",
                        desc_match_type="contains", desc_match_value="emaginenet")
        assert _bank_rule_matches(rule, t) is True


def test_rule_skips_when_disabled(client, test_store_id):
    from app import BankRule, _bank_rule_matches, BankTransaction, db
    _admin_login(client, test_store_id)
    app = client.application
    acct = _make_account(app, test_store_id)
    tid = _make_txn(app, test_store_id, acct, amount_cents=-100,
                    desc="anything")
    with app.app_context():
        t = db.session.get(BankTransaction, tid)
        rule = BankRule(store_id=test_store_id, target_kind="cash_expense",
                        enabled=False, desc_match_type="contains",
                        desc_match_value="anything")
        assert _bank_rule_matches(rule, t) is False


def test_rule_amount_exact_match(client, test_store_id):
    """min == max → exact match."""
    from app import BankRule, _bank_rule_matches, BankTransaction, db
    _admin_login(client, test_store_id)
    app = client.application
    acct = _make_account(app, test_store_id)
    tid_match = _make_txn(app, test_store_id, acct,
                          amount_cents=-18000, desc="EmagineNet", txn_id="t1")
    tid_miss = _make_txn(app, test_store_id, acct,
                         amount_cents=-19000, desc="EmagineNet", txn_id="t2")
    with app.app_context():
        rule = BankRule(store_id=test_store_id, target_kind="check_expense",
                        amount_min_cents=18000, amount_max_cents=18000)
        t1 = db.session.get(BankTransaction, tid_match)
        t2 = db.session.get(BankTransaction, tid_miss)
        assert _bank_rule_matches(rule, t1) is True
        assert _bank_rule_matches(rule, t2) is False


def test_rule_sign_filter_debit(client, test_store_id):
    from app import BankRule, _bank_rule_matches, BankTransaction, db
    _admin_login(client, test_store_id)
    app = client.application
    acct = _make_account(app, test_store_id)
    tid_credit = _make_txn(app, test_store_id, acct,
                           amount_cents=10000, desc="DEPOSIT", txn_id="t_c")
    tid_debit = _make_txn(app, test_store_id, acct,
                          amount_cents=-10000, desc="ACH", txn_id="t_d")
    with app.app_context():
        rule = BankRule(store_id=test_store_id, target_kind="cash_expense",
                        sign_filter="debit")
        assert _bank_rule_matches(rule, db.session.get(BankTransaction, tid_credit)) is False
        assert _bank_rule_matches(rule, db.session.get(BankTransaction, tid_debit)) is True


def test_rule_account_filter(client, test_store_id):
    from app import BankRule, _bank_rule_matches, BankTransaction, db
    _admin_login(client, test_store_id)
    app = client.application
    a1 = _make_account(app, test_store_id, slug="fca_a1", display="A", last4="0210")
    a2 = _make_account(app, test_store_id, slug="fca_a2", display="B", last4="0230")
    tid = _make_txn(app, test_store_id, a1, amount_cents=-100,
                    desc="x", txn_id="t_a")
    with app.app_context():
        rule = BankRule(store_id=test_store_id, target_kind="cash_expense",
                        account_filter_id=a2)
        t = db.session.get(BankTransaction, tid)
        assert _bank_rule_matches(rule, t) is False
        rule.account_filter_id = a1
        assert _bank_rule_matches(rule, t) is True


# ── categorize / uncategorize ────────────────────────────────


def test_categorize_creates_daily_line_item(client, test_store_id):
    """Categorizing into a daily-book kind creates the DailyLineItem
    and links it back via daily_line_item_id."""
    from app import (BankTransaction, DailyLineItem, db,
                     _categorize_bank_transaction)
    _admin_login(client, test_store_id)
    app = client.application
    acct = _make_account(app, test_store_id)
    when = datetime.utcnow().replace(hour=10, minute=0, second=0, microsecond=0)
    tid = _make_txn(app, test_store_id, acct, amount_cents=-18000,
                    desc="EmagineNet ACH", when=when)
    with app.app_context():
        t = db.session.get(BankTransaction, tid)
        _categorize_bank_transaction(t, "check_expense", rule=None, post_to_daily=True)
        db.session.commit()
        t = db.session.get(BankTransaction, tid)
        assert t.category_slug == "check_expense"
        assert t.daily_line_item_id is not None
        line = db.session.get(DailyLineItem, t.daily_line_item_id)
        assert line is not None
        assert line.kind == "check_expense"
        assert line.amount == 180.0  # absolute value
        assert line.report_date == when.date()
        assert line.note == "EmagineNet ACH"


def test_categorize_non_posting_skips_daily_line_item(client, test_store_id):
    """internal_transfer doesn't create a DailyLineItem."""
    from app import BankTransaction, db, _categorize_bank_transaction
    _admin_login(client, test_store_id)
    app = client.application
    acct = _make_account(app, test_store_id)
    tid = _make_txn(app, test_store_id, acct, amount_cents=-40000,
                    desc="PC CU TRANSFER")
    with app.app_context():
        t = db.session.get(BankTransaction, tid)
        _categorize_bank_transaction(t, "internal_transfer",
                                     rule=None, post_to_daily=True)
        db.session.commit()
        t = db.session.get(BankTransaction, tid)
        assert t.category_slug == "internal_transfer"
        assert t.daily_line_item_id is None


def test_recategorize_replaces_daily_line_item(client, test_store_id):
    """Re-categorizing deletes the old DailyLineItem and creates a fresh one."""
    from app import (BankTransaction, DailyLineItem, db,
                     _categorize_bank_transaction)
    _admin_login(client, test_store_id)
    app = client.application
    acct = _make_account(app, test_store_id)
    tid = _make_txn(app, test_store_id, acct, amount_cents=-5000, desc="X")
    with app.app_context():
        t = db.session.get(BankTransaction, tid)
        _categorize_bank_transaction(t, "check_expense", rule=None)
        db.session.commit()
        first_id = db.session.get(BankTransaction, tid).daily_line_item_id
        assert first_id is not None
        # Re-categorize to a different kind
        t = db.session.get(BankTransaction, tid)
        _categorize_bank_transaction(t, "cash_expense", rule=None)
        db.session.commit()
        t = db.session.get(BankTransaction, tid)
        assert t.daily_line_item_id != first_id
        assert db.session.get(DailyLineItem, first_id) is None
        line = db.session.get(DailyLineItem, t.daily_line_item_id)
        assert line.kind == "cash_expense"


def test_categorize_with_explicit_report_date(client, test_store_id):
    """RDC case: bank posted on May 2 but the deposit happened May 1 9 PM.
    Categorizing with an explicit report_date overrides posted_at."""
    from datetime import date as ddate
    from app import (BankTransaction, DailyLineItem, db,
                     _categorize_bank_transaction)
    _admin_login(client, test_store_id)
    app = client.application
    acct = _make_account(app, test_store_id)
    posted = datetime(2026, 5, 2, 9, 30)  # bank posted next morning
    tid = _make_txn(app, test_store_id, acct, amount_cents=12500,
                    desc="REMOTE DEP COUNT#3", when=posted)
    actual = ddate(2026, 5, 1)            # operator's deposit was prior evening
    with app.app_context():
        t = db.session.get(BankTransaction, tid)
        _categorize_bank_transaction(t, "check_deposit", report_date=actual)
        db.session.commit()
        line = db.session.get(DailyLineItem,
                              db.session.get(BankTransaction, tid).daily_line_item_id)
        assert line.report_date == actual


def test_move_date_route_shifts_linked_line(client, test_store_id):
    from datetime import date as ddate
    from app import (BankTransaction, DailyLineItem, db,
                     _categorize_bank_transaction)
    _admin_login(client, test_store_id)
    app = client.application
    acct = _make_account(app, test_store_id)
    tid = _make_txn(app, test_store_id, acct, amount_cents=5000,
                    desc="x", when=datetime(2026, 5, 2, 9, 0))
    with app.app_context():
        t = db.session.get(BankTransaction, tid)
        _categorize_bank_transaction(t, "check_deposit")
        db.session.commit()
    resp = client.post(f"/bank/transactions/{tid}/move-date",
                       data={"report_date": "2026-05-01"},
                       follow_redirects=True)
    assert resp.status_code == 200
    with client.application.app_context():
        t = db.session.get(BankTransaction, tid)
        line = db.session.get(DailyLineItem, t.daily_line_item_id)
        assert line.report_date == ddate(2026, 5, 1)


def test_move_date_route_rejects_invalid_date(client, test_store_id):
    from app import BankTransaction, db, _categorize_bank_transaction
    _admin_login(client, test_store_id)
    app = client.application
    acct = _make_account(app, test_store_id)
    tid = _make_txn(app, test_store_id, acct, amount_cents=1000, desc="x")
    with app.app_context():
        t = db.session.get(BankTransaction, tid)
        _categorize_bank_transaction(t, "check_deposit")
        db.session.commit()
    resp = client.post(f"/bank/transactions/{tid}/move-date",
                       data={"report_date": "not-a-date"},
                       follow_redirects=True)
    assert b"Invalid date" in resp.data


def test_move_date_route_rejects_uncategorized(client, test_store_id):
    """No DailyLineItem to move when transaction is uncategorized."""
    from app import db
    _admin_login(client, test_store_id)
    app = client.application
    acct = _make_account(app, test_store_id)
    tid = _make_txn(app, test_store_id, acct, amount_cents=1000, desc="x")
    resp = client.post(f"/bank/transactions/{tid}/move-date",
                       data={"report_date": "2026-05-01"},
                       follow_redirects=True)
    assert b"isn&#39;t linked" in resp.data or b"isn't linked" in resp.data


def test_uncategorize_deletes_daily_line_item(client, test_store_id):
    from app import (BankTransaction, DailyLineItem, db,
                     _categorize_bank_transaction,
                     _uncategorize_bank_transaction)
    _admin_login(client, test_store_id)
    app = client.application
    acct = _make_account(app, test_store_id)
    tid = _make_txn(app, test_store_id, acct, amount_cents=-1000, desc="X")
    with app.app_context():
        t = db.session.get(BankTransaction, tid)
        _categorize_bank_transaction(t, "check_expense", rule=None)
        db.session.commit()
        line_id = db.session.get(BankTransaction, tid).daily_line_item_id
        t = db.session.get(BankTransaction, tid)
        _uncategorize_bank_transaction(t)
        db.session.commit()
        t = db.session.get(BankTransaction, tid)
        assert t.category_slug == ""
        assert t.daily_line_item_id is None
        assert db.session.get(DailyLineItem, line_id) is None


# ── /bank/rules CRUD smoke ───────────────────────────────────


def test_bank_rules_page_renders(client, test_store_id):
    _admin_login(client, test_store_id)
    resp = client.get("/bank/rules")
    assert resp.status_code == 200
    assert b"Create rule" in resp.data
    assert b"Your rules" in resp.data


def test_create_rule_with_minimum_one_condition(client, test_store_id):
    """At least one condition required (description / sign / amount / account)."""
    _admin_login(client, test_store_id)
    # Empty rule rejected
    resp = client.post("/bank/rules/new", data={"target_kind": "cash_expense"},
                       follow_redirects=True)
    assert b"at least one condition" in resp.data.lower()
    # Description-only rule accepted
    resp = client.post("/bank/rules/new", data={
        "target_kind": "cash_expense",
        "desc_match_type": "contains",
        "desc_match_value": "EmagineNet",
        "enabled": "on",
    }, follow_redirects=True)
    assert resp.status_code == 200
    assert b"Rule created" in resp.data
    from app import BankRule
    with client.application.app_context():
        rules = BankRule.query.filter_by(store_id=test_store_id).all()
        assert len(rules) == 1
        assert rules[0].desc_match_value == "EmagineNet"


def test_rule_toggle_and_delete(client, test_store_id):
    from app import BankRule, db
    _admin_login(client, test_store_id)
    with client.application.app_context():
        r = BankRule(store_id=test_store_id, target_kind="cash_expense",
                     desc_match_type="contains", desc_match_value="x")
        db.session.add(r); db.session.commit()
        rid = r.id
    client.post(f"/bank/rules/{rid}/toggle", follow_redirects=True)
    with client.application.app_context():
        assert db.session.get(BankRule, rid).enabled is False
    client.post(f"/bank/rules/{rid}/delete", follow_redirects=True)
    with client.application.app_context():
        assert db.session.get(BankRule, rid) is None


def test_amount_min_max_inverted_rejected(client, test_store_id):
    _admin_login(client, test_store_id)
    resp = client.post("/bank/rules/new", data={
        "target_kind": "cash_expense",
        "amount_min": "200.00",
        "amount_max": "100.00",
    }, follow_redirects=True)
    assert b"can&#39;t be greater" in resp.data or b"can't be greater" in resp.data
