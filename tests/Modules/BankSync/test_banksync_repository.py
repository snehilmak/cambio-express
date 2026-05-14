"""Unit tests for BankSync.Repositories — accounts, transactions, rules.

The Service + Controller layers (PRs 15-16) compose these into the
/bank/transactions and /bank/rules endpoints.
"""
from datetime import date, datetime, timedelta
from tests._app import db


def _seed_account(store_id, *, nickname="", display_name="",
                    institution_name="Bank", last4="0000",
                    stripe_account_id=None):
    from api.Modules.BankSync.Models import StripeBankAccount
    from tests._app import db
    acc = StripeBankAccount(
        store_id=store_id,
        stripe_account_id=stripe_account_id or f"fcacc_{last4}",
        institution_name=institution_name,
        display_name=display_name,
        last4=last4,
        nickname=nickname,
    )
    db.session.add(acc); db.session.commit()
    return acc.id


def _seed_txn(store_id, account_id, *, amount_cents=-100,
                description="X", category_slug="",
                posted_at=None, stripe_transaction_id=None):
    from api.Modules.BankSync.Models import BankTransaction
    from tests._app import db
    t = BankTransaction(
        store_id=store_id,
        stripe_bank_account_id=account_id,
        stripe_transaction_id=(
            stripe_transaction_id or f"txn_{amount_cents}_{description}"
        ),
        amount_cents=amount_cents,
        description=description,
        category_slug=category_slug,
        posted_at=posted_at or datetime.utcnow(),
        status="posted",
    )
    db.session.add(t); db.session.commit()
    return t.id


def _seed_rule(store_id, *, target_kind="bank_charge_210",
                priority=100, enabled=True, desc_match_value=""):
    from api.Modules.BankSync.Models import BankRule
    from tests._app import db
    r = BankRule(
        store_id=store_id,
        target_kind=target_kind,
        priority=priority,
        enabled=enabled,
        desc_match_type="contains" if desc_match_value else "",
        desc_match_value=desc_match_value,
    )
    db.session.add(r); db.session.commit()
    return r.id


# ── list_accounts ───────────────────────────────────────────


def test_list_accounts_returns_store_scoped(test_store_id):
    from tests._app import app as flask_app, db
    from api.Modules.BankSync.Repositories import list_accounts
    with flask_app.app_context():
        a1 = _seed_account(test_store_id, last4="1111")
        rows = list_accounts(db.session, [test_store_id])
    assert len(rows) == 1
    assert rows[0].id == a1


def test_list_accounts_orders_by_label(test_store_id):
    """Accounts ordered by nickname ?? display_name ?? institution
    (case-insensitive). Stable id tie-break for tests."""
    from tests._app import app as flask_app, db
    from api.Modules.BankSync.Repositories import list_accounts
    with flask_app.app_context():
        _seed_account(test_store_id, nickname="Zebra", last4="9")
        _seed_account(test_store_id, nickname="alpha", last4="1")
        rows = list_accounts(db.session, [test_store_id])
    assert [a.nickname for a in rows] == ["alpha", "Zebra"]


def test_list_accounts_excludes_other_stores(test_store_id):
    from api.Modules.Tenancy.Models import Store
    from tests._app import app as flask_app, db
    from api.Modules.BankSync.Repositories import list_accounts
    with flask_app.app_context():
        s2 = Store(name="Other", slug="other-bank",
                    email="o@x.com", plan="trial")
        db.session.add(s2); db.session.commit()
        _seed_account(s2.id, last4="OTHER")
        _seed_account(test_store_id, last4="MINE")
        rows = list_accounts(db.session, [test_store_id])
    assert {a.last4 for a in rows} == {"MINE"}


# ── BankTransactionFilters.from_query ───────────────────────


def test_txn_filters_parses_dates_and_account_id():
    from api.Modules.BankSync.Repositories import BankTransactionFilters
    f = BankTransactionFilters.from_query({
        "posted_from": "2026-01-01", "posted_to": "2026-12-31",
        "account_id": "42",
    })
    assert f.posted_from == date(2026, 1, 1)
    assert f.posted_to == date(2026, 12, 31)
    assert f.account_id == 42


def test_txn_filters_drops_malformed_dates_and_int():
    from api.Modules.BankSync.Repositories import BankTransactionFilters
    f = BankTransactionFilters.from_query({
        "posted_from": "garbage", "account_id": "abc",
    })
    assert f.posted_from is None
    assert f.account_id is None


def test_txn_filters_normalizes_sign_and_uncategorized_only():
    from api.Modules.BankSync.Repositories import BankTransactionFilters
    f = BankTransactionFilters.from_query({
        "sign": "DEBIT", "uncategorized_only": "true",
    })
    assert f.sign == "debit"
    assert f.uncategorized_only is True
    f2 = BankTransactionFilters.from_query({"sign": "garbage"})
    assert f2.sign == ""


# ── list_transactions ───────────────────────────────────────


def test_list_transactions_orders_by_posted_at_desc(test_store_id):
    from tests._app import app as flask_app, db
    from api.Modules.BankSync.Repositories import (
        BankTransactionFilters, list_transactions,
    )
    with flask_app.app_context():
        a = _seed_account(test_store_id)
        old = datetime.utcnow() - timedelta(days=2)
        new = datetime.utcnow()
        _seed_txn(test_store_id, a, description="OLD", posted_at=old)
        _seed_txn(test_store_id, a, description="NEW", posted_at=new)
        rows, total = list_transactions(
            db.session, [test_store_id], BankTransactionFilters(),
        )
    assert total == 2
    assert [r.description for r in rows] == ["NEW", "OLD"]


def test_list_transactions_filters_by_sign(test_store_id):
    from tests._app import app as flask_app, db
    from api.Modules.BankSync.Repositories import (
        BankTransactionFilters, list_transactions,
    )
    with flask_app.app_context():
        a = _seed_account(test_store_id)
        _seed_txn(test_store_id, a, amount_cents=-100, description="DEBIT")
        _seed_txn(test_store_id, a, amount_cents=200, description="CREDIT")
        rows, _ = list_transactions(
            db.session, [test_store_id],
            BankTransactionFilters(sign="credit"),
        )
    assert {r.description for r in rows} == {"CREDIT"}


def test_list_transactions_filters_by_account_id(test_store_id):
    from tests._app import app as flask_app, db
    from api.Modules.BankSync.Repositories import (
        BankTransactionFilters, list_transactions,
    )
    with flask_app.app_context():
        a1 = _seed_account(test_store_id, last4="1111")
        a2 = _seed_account(test_store_id, last4="2222")
        _seed_txn(test_store_id, a1, description="A1")
        _seed_txn(test_store_id, a2, description="A2")
        rows, _ = list_transactions(
            db.session, [test_store_id],
            BankTransactionFilters(account_id=a1),
        )
    assert {r.description for r in rows} == {"A1"}


def test_list_transactions_filters_by_category_and_uncategorized(test_store_id):
    from tests._app import app as flask_app, db
    from api.Modules.BankSync.Repositories import (
        BankTransactionFilters, list_transactions,
    )
    with flask_app.app_context():
        a = _seed_account(test_store_id)
        _seed_txn(test_store_id, a, category_slug="bank_charge_210",
                    description="TAGGED")
        _seed_txn(test_store_id, a, category_slug="",
                    description="UNTAGGED")
        # Specific slug.
        rows, _ = list_transactions(
            db.session, [test_store_id],
            BankTransactionFilters(category_slug="bank_charge_210"),
        )
        assert {r.description for r in rows} == {"TAGGED"}
        # uncategorized_only.
        rows, _ = list_transactions(
            db.session, [test_store_id],
            BankTransactionFilters(uncategorized_only=True),
        )
    assert {r.description for r in rows} == {"UNTAGGED"}


def test_list_transactions_filters_by_q_description(test_store_id):
    from tests._app import app as flask_app, db
    from api.Modules.BankSync.Repositories import (
        BankTransactionFilters, list_transactions,
    )
    with flask_app.app_context():
        a = _seed_account(test_store_id)
        _seed_txn(test_store_id, a, description="REMOTE DEPOSIT FEE")
        _seed_txn(test_store_id, a, description="ACH DEPOSIT")
        rows, _ = list_transactions(
            db.session, [test_store_id],
            BankTransactionFilters(q="remote"),
        )
    assert {r.description for r in rows} == {"REMOTE DEPOSIT FEE"}


def test_list_transactions_paginates(test_store_id):
    from tests._app import app as flask_app, db
    from api.Modules.BankSync.Repositories import (
        BankTransactionFilters, list_transactions,
    )
    with flask_app.app_context():
        a = _seed_account(test_store_id)
        for i in range(5):
            _seed_txn(test_store_id, a,
                       stripe_transaction_id=f"t{i}",
                       description=f"TXN{i}")
        rows, total = list_transactions(
            db.session, [test_store_id], BankTransactionFilters(),
            page=1, per_page=2,
        )
    assert total == 5
    assert len(rows) == 2


# ── sum_amount_cents_by_category ────────────────────────────


def test_sum_amount_returns_absolute_value(test_store_id):
    """The Σ uses ABS(amount_cents) so the P&L card displays the
    positive "we paid this much in fees" number."""
    from tests._app import app as flask_app, db
    from api.Modules.BankSync.Repositories import sum_amount_cents_by_category
    with flask_app.app_context():
        a = _seed_account(test_store_id)
        _seed_txn(test_store_id, a, amount_cents=-210,
                    category_slug="bank_charge_210",
                    description="FEE-1")
        _seed_txn(test_store_id, a, amount_cents=-500,
                    category_slug="bank_charge_210",
                    description="FEE-2")
        # Different slug — must be excluded.
        _seed_txn(test_store_id, a, amount_cents=-999,
                    category_slug="other_kind",
                    description="OTHER")
        result = sum_amount_cents_by_category(
            db.session, [test_store_id], "bank_charge_210",
        )
    assert result == 710


def test_sum_amount_zero_for_empty(test_store_id):
    from tests._app import app as flask_app, db
    from api.Modules.BankSync.Repositories import sum_amount_cents_by_category
    with flask_app.app_context():
        result = sum_amount_cents_by_category(
            db.session, [test_store_id], "bank_charge_210",
        )
    assert result == 0


# ── list_rules ──────────────────────────────────────────────


def test_list_rules_orders_by_priority_then_id(test_store_id):
    from tests._app import app as flask_app, db
    from api.Modules.BankSync.Repositories import list_rules
    with flask_app.app_context():
        r_high = _seed_rule(test_store_id, priority=10,
                              desc_match_value="HIGH")
        r_low = _seed_rule(test_store_id, priority=100,
                              desc_match_value="LOW")
        r_dup = _seed_rule(test_store_id, priority=10,
                              desc_match_value="DUP")
        rows = list_rules(db.session, [test_store_id])
    # priority 10 first, id asc within. r_high.id < r_dup.id.
    assert [r.id for r in rows] == [r_high, r_dup, r_low]


def test_list_rules_enabled_only_filter(test_store_id):
    from tests._app import app as flask_app, db
    from api.Modules.BankSync.Repositories import list_rules
    with flask_app.app_context():
        r_on = _seed_rule(test_store_id, desc_match_value="ON",
                            enabled=True)
        _seed_rule(test_store_id, desc_match_value="OFF",
                     enabled=False)
        rows = list_rules(
            db.session, [test_store_id], enabled_only=True,
        )
    assert [r.id for r in rows] == [r_on]
