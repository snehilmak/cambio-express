"""Unit tests for BankSync.Services.applier (PR 71)."""
from datetime import datetime
from unittest.mock import MagicMock
from tests._app import db


def _store_with_account(db, *, slug="applier-store", last4="0210"):
    """Set up a store + a connected `StripeBankAccount`."""
    from api.Modules.BankSync.Models import StripeBankAccount
    from api.Modules.Tenancy.Models import Store
    s = Store(name=slug, slug=slug, plan="basic",
              email=f"{slug}@example.com")
    db.add(s); db.flush()
    a = StripeBankAccount(
        store_id=s.id,
        stripe_account_id=f"fcacct_{slug}",
        last4=last4,
    )
    db.add(a); db.flush()
    return s, a


_TXN_COUNTER = [0]


def _add_uncategorized_txn(db, store_id, account_id,
                            *, description="REMOTE DEPOSIT FEE",
                            amount_cents=-210):
    from api.Modules.BankSync.Models import BankTransaction
    _TXN_COUNTER[0] += 1
    t = BankTransaction(
        store_id=store_id,
        stripe_bank_account_id=account_id,
        stripe_transaction_id=f"txn_applier_{_TXN_COUNTER[0]}",
        amount_cents=amount_cents,
        posted_at=datetime.utcnow(),
        description=description,
        category_slug="",
    )
    db.add(t); db.flush()
    return t


# ── idempotency ────────────────────────────────────────────


def test_already_categorized_row_is_skipped():
    """Rows with a non-empty category_slug must NOT be retagged
    — operator overrides survive."""
    from tests._app import app as flask_app, db
    from api.Modules.BankSync.Services import (
        apply_rules_to_uncategorized_row,
    )
    with flask_app.app_context():
        s, a = _store_with_account(db.session, slug="idem-store")
        t = _add_uncategorized_txn(db.session, s.id, a.id)
        t.category_slug = "manual_override"
        db.session.flush()
        result = apply_rules_to_uncategorized_row(
            db.session, t, a, allow_auto_post=True,
        )
        assert result is False
        assert t.category_slug == "manual_override"


# ── built-in rule path ────────────────────────────────────


def test_matches_builtin_when_no_operator_rule():
    """REMOTE DEPOSIT FEE on the 0230 MSB account fires the
    Nizari built-in. Built-ins never post to the daily book."""
    from api.Modules.BankSync.Models import BankRule
    from tests._app import app as flask_app, db
    from api.Modules.BankSync.Services import (
        apply_rules_to_uncategorized_row,
    )
    with flask_app.app_context():
        db.session.query(BankRule).delete()
        db.session.commit()
        s, a = _store_with_account(
            db.session, slug="rdc-store", last4="0230",
        )
        t = _add_uncategorized_txn(
            db.session, s.id, a.id,
            description="REMOTE DEPOSIT FEE 04/29",
        )
        result = apply_rules_to_uncategorized_row(
            db.session, t, a, allow_auto_post=True,
        )
        assert result is True
        # Built-in resolves bank_charge_per_account → bank_charge_<last4>
        assert t.category_slug == "bank_charge_230"


def test_no_match_leaves_row_uncategorised():
    from api.Modules.BankSync.Models import BankRule
    from tests._app import app as flask_app, db
    from api.Modules.BankSync.Services import (
        apply_rules_to_uncategorized_row,
    )
    with flask_app.app_context():
        db.session.query(BankRule).delete()
        db.session.commit()
        s, a = _store_with_account(
            db.session, slug="nomatch-store", last4="9999",
        )
        # Description that no built-in matches.
        t = _add_uncategorized_txn(
            db.session, s.id, a.id,
            description="MISC TRANSACTION",
        )
        result = apply_rules_to_uncategorized_row(
            db.session, t, a, allow_auto_post=True,
        )
        assert result is False
        assert (t.category_slug or "") == ""


# ── operator rule path ────────────────────────────────────


def test_operator_rule_wins_over_builtin():
    """Operator rules fire before built-ins. Rule chain order
    matters."""
    from api.Modules.BankSync.Models import BankRule
    from tests._app import app as flask_app, db
    from api.Modules.BankSync.Services import (
        apply_rules_to_uncategorized_row,
    )
    with flask_app.app_context():
        db.session.query(BankRule).delete()
        db.session.commit()
        s, a = _store_with_account(
            db.session, slug="opwin-store", last4="0230",
        )
        # An operator rule that matches "REMOTE DEPOSIT FEE" with
        # a different target_kind than the built-in's.
        db.session.add(BankRule(
            store_id=s.id, priority=0, enabled=True,
            desc_match_type="contains",
            desc_match_value="REMOTE DEPOSIT FEE",
            target_kind="ignore",
            auto_post=False,
            description="op rule wins",
        ))
        t = _add_uncategorized_txn(
            db.session, s.id, a.id,
            description="REMOTE DEPOSIT FEE 04/29",
        )
        result = apply_rules_to_uncategorized_row(
            db.session, t, a, allow_auto_post=True,
        )
        assert result is True
        # Operator rule's target_kind wins — not the built-in's.
        assert t.category_slug == "ignore"


def test_operator_rule_increments_match_count():
    """When an operator rule fires, its match_count goes up +
    last_matched_at gets stamped."""
    from api.Modules.BankSync.Models import BankRule
    from tests._app import app as flask_app, db
    from api.Modules.BankSync.Services import (
        apply_rules_to_uncategorized_row,
    )
    with flask_app.app_context():
        db.session.query(BankRule).delete()
        db.session.commit()
        s, a = _store_with_account(db.session, slug="counter-store")
        rule = BankRule(
            store_id=s.id, priority=0, enabled=True,
            desc_match_type="contains",
            desc_match_value="UTILITY",
            target_kind="ignore",
            auto_post=False,
            description="utility tag",
        )
        db.session.add(rule); db.session.flush()
        before = rule.match_count or 0
        t = _add_uncategorized_txn(
            db.session, s.id, a.id, description="UTILITY BILL",
        )
        apply_rules_to_uncategorized_row(
            db.session, t, a, allow_auto_post=False,
        )
        assert (rule.match_count or 0) == before + 1
        assert rule.last_matched_at is not None


# ── auto_post gating ───────────────────────────────────────


def test_allow_auto_post_false_skips_daily_line_item():
    """allow_auto_post=False (backfill mode) → don't create
    DailyLineItem even when rule.auto_post=True."""
    from api.Modules.BankSync.Models import BankRule
    from api.Modules.DailyBook.Models import DailyLineItem
    from tests._app import app as flask_app, db
    from api.Modules.BankSync.Services import (
        apply_rules_to_uncategorized_row,
    )
    with flask_app.app_context():
        db.session.query(BankRule).delete()
        db.session.query(DailyLineItem).delete()
        db.session.commit()
        s, a = _store_with_account(db.session, slug="backfill-store")
        db.session.add(BankRule(
            store_id=s.id, priority=0, enabled=True,
            desc_match_type="contains",
            desc_match_value="OFFICE",
            target_kind="cash_expense",
            auto_post=True,  # rule WANTS to auto-post
            description="office supplies",
        ))
        t = _add_uncategorized_txn(
            db.session, s.id, a.id,
            description="OFFICE DEPOT", amount_cents=-1500,
        )
        apply_rules_to_uncategorized_row(
            db.session, t, a, allow_auto_post=False,  # backfill
        )
        # Tagged but no daily-book row created.
        assert t.category_slug == "cash_expense"
        assert t.daily_line_item_id is None
        assert db.session.query(DailyLineItem).filter_by(
            store_id=s.id,
        ).count() == 0


def test_allow_auto_post_true_creates_daily_line_item():
    """allow_auto_post=True + rule.auto_post=True + daily-book
    target → DailyLineItem created."""
    from api.Modules.BankSync.Models import BankRule
    from api.Modules.DailyBook.Models import DailyLineItem
    from tests._app import app as flask_app, db
    from api.Modules.BankSync.Services import (
        apply_rules_to_uncategorized_row,
    )
    with flask_app.app_context():
        db.session.query(BankRule).delete()
        db.session.query(DailyLineItem).delete()
        db.session.commit()
        s, a = _store_with_account(db.session, slug="autopost-store")
        db.session.add(BankRule(
            store_id=s.id, priority=0, enabled=True,
            desc_match_type="contains",
            desc_match_value="OFFICE",
            target_kind="cash_expense",
            auto_post=True,
            description="office supplies",
        ))
        t = _add_uncategorized_txn(
            db.session, s.id, a.id,
            description="OFFICE DEPOT", amount_cents=-1500,
        )
        apply_rules_to_uncategorized_row(
            db.session, t, a, allow_auto_post=True,  # fresh row
        )
        # Tagged AND daily-book row created.
        assert t.category_slug == "cash_expense"
        assert t.daily_line_item_id is not None


# ── legacy Flask wrapper ──────────────────────────────────


