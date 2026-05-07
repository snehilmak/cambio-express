"""Unit tests for BankSync.Services.categorize (PR 36)."""
from datetime import date, datetime, time


def _seed_account(store_id, *, last4="0000"):
    from app import StripeBankAccount, db
    a = StripeBankAccount(
        store_id=store_id, stripe_account_id=f"fcacc_{last4}",
        institution_name="Bank", last4=last4, enabled=True,
    )
    db.session.add(a); db.session.commit()
    return a.id


def _seed_txn(store_id, account_id, *, amount_cents=-100,
                description="X", category_slug=""):
    from app import BankTransaction, db
    t = BankTransaction(
        store_id=store_id,
        stripe_bank_account_id=account_id,
        stripe_transaction_id=f"txn_{description}_{amount_cents}",
        amount_cents=amount_cents,
        description=description,
        category_slug=category_slug,
        posted_at=datetime(2026, 5, 6, 10, 0, 0),
        status="posted",
    )
    db.session.add(t); db.session.commit()
    return t


def _is_daily(slug):
    """Stand-in for the legacy `_is_daily_book_kind`. cash_expense is
    on the daily-book kinds list."""
    return slug in {"cash_expense", "cash_purchase", "check_expense"}


# ── categorize_transaction ──────────────────────────────────


def test_categorize_sets_category_slug(test_store_id):
    from app import app as flask_app, db
    from api.Modules.BankSync.Services import categorize_transaction
    with flask_app.app_context():
        a = _seed_account(test_store_id)
        txn = _seed_txn(test_store_id, a, description="FEE")
        categorize_transaction(
            db.session, txn, "bank_charge_210",
            post_to_daily=False,
        )
        db.session.commit()
        assert txn.category_slug == "bank_charge_210"


def test_categorize_creates_daily_line_item_for_daily_kind(test_store_id):
    """A daily-book kind + post_to_daily=True creates a linked
    DailyLineItem."""
    from app import app as flask_app, db, DailyLineItem
    from api.Modules.BankSync.Services import categorize_transaction
    with flask_app.app_context():
        a = _seed_account(test_store_id)
        txn = _seed_txn(test_store_id, a, description="FEE",
                          amount_cents=-2510)
        categorize_transaction(
            db.session, txn, "cash_expense",
            post_to_daily=True, is_daily_book_kind=_is_daily,
        )
        db.session.commit()
        assert txn.daily_line_item_id is not None
        line = db.session.get(DailyLineItem, txn.daily_line_item_id)
        assert line.kind == "cash_expense"
        # Absolute value, dollars not cents
        assert line.amount == 25.10


def test_categorize_skips_daily_for_non_daily_kind(test_store_id):
    """bank_charge_210 isn't a daily-book kind — no DailyLineItem
    should be created."""
    from app import app as flask_app, db
    from api.Modules.BankSync.Services import categorize_transaction
    with flask_app.app_context():
        a = _seed_account(test_store_id)
        txn = _seed_txn(test_store_id, a)
        categorize_transaction(
            db.session, txn, "bank_charge_210",
            post_to_daily=True, is_daily_book_kind=_is_daily,
        )
        db.session.commit()
        assert txn.category_slug == "bank_charge_210"
        assert txn.daily_line_item_id is None


def test_categorize_idempotent_on_re_categorize(test_store_id):
    """Re-categorizing should drop the prior DailyLineItem before
    creating a fresh one — no orphan rows."""
    from app import app as flask_app, db, DailyLineItem
    from api.Modules.BankSync.Services import categorize_transaction
    with flask_app.app_context():
        a = _seed_account(test_store_id)
        txn = _seed_txn(test_store_id, a)
        # First categorize → daily kind
        categorize_transaction(
            db.session, txn, "cash_expense",
            post_to_daily=True, is_daily_book_kind=_is_daily,
        )
        db.session.commit()
        first_line_id = txn.daily_line_item_id
        # Re-categorize as a different daily kind
        categorize_transaction(
            db.session, txn, "cash_purchase",
            post_to_daily=True, is_daily_book_kind=_is_daily,
        )
        db.session.commit()
        # Old line removed
        assert db.session.get(DailyLineItem, first_line_id) is None
        # New line linked
        assert txn.daily_line_item_id != first_line_id


def test_categorize_with_rule_increments_match_count(test_store_id):
    from app import app as flask_app, db, BankRule
    from api.Modules.BankSync.Services import categorize_transaction
    with flask_app.app_context():
        a = _seed_account(test_store_id)
        txn = _seed_txn(test_store_id, a)
        rule = BankRule(
            store_id=test_store_id,
            target_kind="bank_charge_210",
            sign_filter="debit",
            match_count=5,
        )
        db.session.add(rule); db.session.commit()
        categorize_transaction(
            db.session, txn, "bank_charge_210",
            rule=rule, post_to_daily=False,
        )
        db.session.commit()
        assert rule.match_count == 6
        assert rule.last_matched_at is not None
        assert txn.matched_rule_id == rule.id


def test_categorize_uses_report_date_override(test_store_id):
    """When report_date is passed, the DailyLineItem uses that date
    instead of the transaction's posted_at date."""
    from app import app as flask_app, db, DailyLineItem
    from api.Modules.BankSync.Services import categorize_transaction
    with flask_app.app_context():
        a = _seed_account(test_store_id)
        txn = _seed_txn(test_store_id, a)
        override = date(2026, 5, 5)
        categorize_transaction(
            db.session, txn, "cash_expense",
            post_to_daily=True, report_date=override,
            is_daily_book_kind=_is_daily,
        )
        db.session.commit()
        line = db.session.get(DailyLineItem, txn.daily_line_item_id)
        assert line.report_date == override


# ── uncategorize_transaction ────────────────────────────────


def test_uncategorize_clears_slug_and_removes_line(test_store_id):
    from app import app as flask_app, db, DailyLineItem
    from api.Modules.BankSync.Services import (
        categorize_transaction, uncategorize_transaction,
    )
    with flask_app.app_context():
        a = _seed_account(test_store_id)
        txn = _seed_txn(test_store_id, a)
        categorize_transaction(
            db.session, txn, "cash_expense",
            post_to_daily=True, is_daily_book_kind=_is_daily,
        )
        db.session.commit()
        line_id = txn.daily_line_item_id
        # Now uncategorize
        uncategorize_transaction(db.session, txn)
        db.session.commit()
        assert txn.category_slug == ""
        assert txn.matched_rule_id is None
        assert txn.daily_line_item_id is None
        assert db.session.get(DailyLineItem, line_id) is None


def test_uncategorize_safe_when_already_unset(test_store_id):
    from app import app as flask_app, db
    from api.Modules.BankSync.Services import uncategorize_transaction
    with flask_app.app_context():
        a = _seed_account(test_store_id)
        txn = _seed_txn(test_store_id, a)
        # Already uncategorized
        uncategorize_transaction(db.session, txn)
        db.session.commit()
        assert txn.category_slug == ""
