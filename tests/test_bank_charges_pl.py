"""Built-in bank-charge auto-categorisation + monthly P&L feed.

Built-in (platform-managed) rules fire on sync after user-defined
rules don't match. They tag specific transactions like Nizari's
"REMOTE DEPOSIT FEE" → bank_charge_230 so the operator never has
to set up their own rule for these standard charges. The tagged
transactions feed MonthlyFinancial.bank_charges_210 / _230 via
_bank_charges_for_month so the P&L picks them up automatically.
"""
from datetime import datetime


def _admin_login(client, store_id, *, plan="pro"):
    from app import User, Store, db
    with client.application.app_context():
        u = User.query.filter_by(store_id=store_id, role="admin").first()
        uid = u.id
        s = db.session.get(Store, store_id)
        s.plan = plan
        s.billing_cycle = "monthly"
        db.session.commit()
    with client.session_transaction() as s:
        s["user_id"] = uid
        s["role"] = "admin"
        s["store_id"] = store_id
    return client


def _make_account(app, store_id, *, last4, slug=None, display="Acct"):
    from app import StripeBankAccount, db
    with app.app_context():
        a = StripeBankAccount(
            store_id=store_id, stripe_account_id=slug or f"fca_{last4}",
            display_name=display, last4=last4, currency="usd",
        )
        db.session.add(a); db.session.commit()
        return a.id


def _make_txn(app, store_id, acct_id, *, amount_cents, desc, when=None,
              txn_id="fctxn_x"):
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


# ── _match_builtin_bank_rule ─────────────────────────────────


def test_builtin_remote_deposit_fee_on_msb_account_matches(client, test_store_id):
    """Nizari's MSB ••0230 RDC fee is the canonical built-in rule."""
    from app import (BankTransaction, StripeBankAccount, db,
                     _match_builtin_bank_rule)
    _admin_login(client, test_store_id)
    app = client.application
    aid = _make_account(app, test_store_id, last4="0230")
    tid = _make_txn(app, test_store_id, aid, amount_cents=-210,
                    desc="REMOTE DEPOSIT FEE 04/29")
    with app.app_context():
        t = db.session.get(BankTransaction, tid)
        a = db.session.get(StripeBankAccount, aid)
        assert _match_builtin_bank_rule(t, a) == "bank_charge_230"


def test_builtin_rule_account_filter_blocks_wrong_account(client, test_store_id):
    """Same description on the ••0210 (non-MSB) account doesn't fire."""
    from app import (BankTransaction, StripeBankAccount, db,
                     _match_builtin_bank_rule)
    _admin_login(client, test_store_id)
    app = client.application
    aid = _make_account(app, test_store_id, last4="0210")
    tid = _make_txn(app, test_store_id, aid, amount_cents=-210,
                    desc="REMOTE DEPOSIT FEE")
    with app.app_context():
        t = db.session.get(BankTransaction, tid)
        a = db.session.get(StripeBankAccount, aid)
        assert _match_builtin_bank_rule(t, a) is None


def test_builtin_rule_no_match_returns_none(client, test_store_id):
    from app import (BankTransaction, StripeBankAccount, db,
                     _match_builtin_bank_rule)
    _admin_login(client, test_store_id)
    app = client.application
    aid = _make_account(app, test_store_id, last4="0230")
    tid = _make_txn(app, test_store_id, aid, amount_cents=-1000,
                    desc="ACH/SOMETHING ELSE")
    with app.app_context():
        t = db.session.get(BankTransaction, tid)
        a = db.session.get(StripeBankAccount, aid)
        assert _match_builtin_bank_rule(t, a) is None


def test_builtin_rule_case_insensitive(client, test_store_id):
    """Banks sometimes vary case on descriptions; match comparing on uppercase."""
    from app import (BankTransaction, StripeBankAccount, db,
                     _match_builtin_bank_rule)
    _admin_login(client, test_store_id)
    app = client.application
    aid = _make_account(app, test_store_id, last4="0230")
    tid = _make_txn(app, test_store_id, aid, amount_cents=-210,
                    desc="Remote Deposit Fee")
    with app.app_context():
        t = db.session.get(BankTransaction, tid)
        a = db.session.get(StripeBankAccount, aid)
        assert _match_builtin_bank_rule(t, a) == "bank_charge_230"


# ── _bank_charges_for_month ──────────────────────────────────


def test_bank_charges_for_month_returns_absolute_value(client, test_store_id):
    """Bank-charge transactions have negative cents (debits); the P&L
    expense column wants positive."""
    from app import db, _bank_charges_for_month
    _admin_login(client, test_store_id)
    app = client.application
    aid = _make_account(app, test_store_id, last4="0230")
    when = datetime(2026, 5, 12, 9, 0)
    from app import BankTransaction
    with app.app_context():
        for i, cents in enumerate([-210, -150]):
            db.session.add(BankTransaction(
                store_id=test_store_id, stripe_bank_account_id=aid,
                stripe_transaction_id=f"bc_{i}",
                amount_cents=cents, description="REMOTE DEPOSIT FEE",
                posted_at=when, status="posted",
                category_slug="bank_charge_230",
            ))
        db.session.commit()
        total = _bank_charges_for_month(test_store_id, 2026, 5, "bank_charge_230")
        assert total == 3.60


def test_bank_charges_for_month_filters_by_category(client, test_store_id):
    """A 0210 charge in the same month doesn't leak into the 230 sum."""
    from app import BankTransaction, db, _bank_charges_for_month
    _admin_login(client, test_store_id)
    app = client.application
    a210 = _make_account(app, test_store_id, last4="0210", slug="fca_a210")
    a230 = _make_account(app, test_store_id, last4="0230", slug="fca_a230")
    when = datetime(2026, 5, 10)
    with app.app_context():
        db.session.add(BankTransaction(
            store_id=test_store_id, stripe_bank_account_id=a210,
            stripe_transaction_id="bc_210", amount_cents=-500,
            description="Some 210 fee", posted_at=when,
            status="posted", category_slug="bank_charge_210",
        ))
        db.session.add(BankTransaction(
            store_id=test_store_id, stripe_bank_account_id=a230,
            stripe_transaction_id="bc_230", amount_cents=-210,
            description="REMOTE DEPOSIT FEE", posted_at=when,
            status="posted", category_slug="bank_charge_230",
        ))
        db.session.commit()
        assert _bank_charges_for_month(test_store_id, 2026, 5, "bank_charge_210") == 5.00
        assert _bank_charges_for_month(test_store_id, 2026, 5, "bank_charge_230") == 2.10


def test_bank_charges_for_month_filters_by_month(client, test_store_id):
    """An April charge doesn't roll into the May P&L."""
    from app import BankTransaction, db, _bank_charges_for_month
    _admin_login(client, test_store_id)
    app = client.application
    aid = _make_account(app, test_store_id, last4="0230")
    with app.app_context():
        db.session.add(BankTransaction(
            store_id=test_store_id, stripe_bank_account_id=aid,
            stripe_transaction_id="bc_apr", amount_cents=-100,
            description="x", posted_at=datetime(2026, 4, 30, 23, 59),
            status="posted", category_slug="bank_charge_230",
        ))
        db.session.add(BankTransaction(
            store_id=test_store_id, stripe_bank_account_id=aid,
            stripe_transaction_id="bc_may", amount_cents=-200,
            description="y", posted_at=datetime(2026, 5, 1, 0, 1),
            status="posted", category_slug="bank_charge_230",
        ))
        db.session.commit()
        assert _bank_charges_for_month(test_store_id, 2026, 4, "bank_charge_230") == 1.00
        assert _bank_charges_for_month(test_store_id, 2026, 5, "bank_charge_230") == 2.00


def test_bank_charges_for_month_zero_when_no_matches(client, test_store_id):
    """No tagged transactions → 0.0 → monthly_report will leave the
    manual P&L value editable (not LOCKed)."""
    from app import _bank_charges_for_month
    _admin_login(client, test_store_id)
    with client.application.app_context():
        assert _bank_charges_for_month(test_store_id, 2026, 5, "bank_charge_230") == 0.0


# ── monthly_report end-to-end ────────────────────────────────


def test_monthly_report_renders_locked_bank_charge_amount(client, test_store_id):
    """Regression for the bug where the auto value was computed but the
    template still rendered report.bank_charges_230 (= 0). The locked
    field must show the auto-computed dollars."""
    from app import BankTransaction, db
    _admin_login(client, test_store_id)
    app = client.application
    aid = _make_account(app, test_store_id, last4="0230")
    when = datetime(2026, 5, 12, 9, 0)
    with app.app_context():
        db.session.add(BankTransaction(
            store_id=test_store_id, stripe_bank_account_id=aid,
            stripe_transaction_id="rdc_1", amount_cents=-210,
            description="REMOTE DEPOSIT FEE", posted_at=when,
            status="posted", category_slug="bank_charge_230",
        ))
        db.session.commit()
    body = client.get("/monthly/2026/5").data.decode()
    assert 'name="bank_charges_230"' in body
    assert 'value="2.10"' in body
    assert "Locked · bank sync" in body


def test_monthly_report_post_persists_locked_bank_charge(client, test_store_id):
    """Saving the form forces the locked auto value into the row even
    when the form payload sends 0 (or anything else). Guards against a
    stale tab POSTing pre-categorisation values back."""
    from app import BankTransaction, MonthlyFinancial, db
    _admin_login(client, test_store_id)
    app = client.application
    aid = _make_account(app, test_store_id, last4="0230")
    when = datetime(2026, 6, 10, 12, 0)
    with app.app_context():
        db.session.add(BankTransaction(
            store_id=test_store_id, stripe_bank_account_id=aid,
            stripe_transaction_id="rdc_2", amount_cents=-300,
            description="REMOTE DEPOSIT FEE", posted_at=when,
            status="posted", category_slug="bank_charge_230",
        ))
        db.session.commit()
    client.post("/monthly/2026/6", data={
        "bank_charges_230": "999.99",
    }, follow_redirects=True)
    with app.app_context():
        row = MonthlyFinancial.query.filter_by(
            store_id=test_store_id, year=2026, month=6).first()
        assert row.bank_charges_230 == 3.00


def test_monthly_report_leaves_field_editable_when_no_charges(client, test_store_id):
    """No tagged transactions → field rendered editable, manual entry
    preserved on POST. Backward-compat for stores without bank sync."""
    from app import MonthlyFinancial
    _admin_login(client, test_store_id)
    body = client.get("/monthly/2026/7").data.decode()
    assert 'name="bank_charges_230"' in body
    assert "Locked · bank sync" not in body
    client.post("/monthly/2026/7", data={
        "bank_charges_230": "42.50",
    }, follow_redirects=True)
    with client.application.app_context():
        row = MonthlyFinancial.query.filter_by(
            store_id=test_store_id, year=2026, month=7).first()
        assert row.bank_charges_230 == 42.50


# ── Registry-driven generic auto-feed ────────────────────────


def test_registry_drives_monthly_auto_for_every_mapped_category(
        client, test_store_id):
    """Every entry in _BANK_CATEGORY_PL_FIELD must auto-flow into its
    mapped column on the monthly P&L. This is what guarantees that
    adding a new built-in rule + new registry row "just works" without
    bespoke wiring in monthly_report()."""
    from app import (BankTransaction, MonthlyFinancial,
                     _BANK_CATEGORY_PL_FIELD, db)
    _admin_login(client, test_store_id)
    app = client.application
    when = datetime(2026, 8, 15, 10, 0)

    # Seed one tagged transaction per registry entry, distinct amount
    # so we can assert each lands on the right column.
    expected = {}
    with app.app_context():
        for i, (slug, field) in enumerate(_BANK_CATEGORY_PL_FIELD.items()):
            aid = _make_account(app, test_store_id,
                                last4=f"99{i:02d}",
                                slug=f"fca_reg_{i}")
            cents = -(100 * (i + 1))
            db.session.add(BankTransaction(
                store_id=test_store_id, stripe_bank_account_id=aid,
                stripe_transaction_id=f"reg_{i}",
                amount_cents=cents, description="x",
                posted_at=when, status="posted",
                category_slug=slug,
            ))
            expected[field] = abs(cents) / 100.0
        db.session.commit()

    body = client.get("/monthly/2026/8").data.decode()
    for field, dollars in expected.items():
        assert f'name="{field}"' in body
        assert f'value="{dollars:.2f}"' in body, (
            f"{field}: expected value=\"{dollars:.2f}\" in rendered P&L")

    # POST should also force the locked auto value over any payload.
    payload = {field: "999.99" for field in expected}
    client.post("/monthly/2026/8", data=payload, follow_redirects=True)
    with app.app_context():
        row = MonthlyFinancial.query.filter_by(
            store_id=test_store_id, year=2026, month=8).first()
        for field, dollars in expected.items():
            assert getattr(row, field) == dollars, (
                f"{field}: server should have forced auto value, "
                f"got {getattr(row, field)} instead of {dollars}")
