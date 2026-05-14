"""Unit tests for BankSync.Services.sync (PR 72).

The full sync orchestrator hits the Stripe FC API; we mock the
SDK calls. The supporting helpers (`upsert_bank_transaction`,
`backfill_uncategorized_rows`, `migrate_generic_bank_charge_per_
account`) are testable directly against the real ORM.
"""
from datetime import datetime
from unittest.mock import MagicMock, patch


_TXN_COUNTER = [0]


def _stripe_txn_dict(*, txn_id=None, amount=-210, currency="usd",
                     description="REMOTE DEPOSIT FEE",
                     status="posted", transacted_at=None):
    """Stripe FC Transaction dict (matches the API response shape
    we read in `upsert_bank_transaction`)."""
    _TXN_COUNTER[0] += 1
    return {
        "id": txn_id or f"fc_txn_test_{_TXN_COUNTER[0]}",
        "amount": amount,
        "currency": currency,
        "description": description,
        "status": status,
        "transacted_at": transacted_at,
    }


def _store_with_account(db, *, slug="sync-store", last4="0230"):
    from api.Modules.BankSync.Models import StripeBankAccount
    from api.Modules.Tenancy.Models import Store
    s = Store(name=slug, slug=slug, plan="basic",
              email=f"{slug}@example.com")
    db.add(s); db.flush()
    a = StripeBankAccount(
        store_id=s.id,
        stripe_account_id=f"fcacct_{slug}",
        last4=last4,
        enabled=True,
    )
    db.add(a); db.flush()
    return s, a


# ── upsert_bank_transaction ────────────────────────────────


def test_upsert_inserts_new_row():
    from api.Modules.BankSync.Models import BankTransaction
    from tests._app import app as flask_app, db
    from api.Modules.BankSync.Services import upsert_bank_transaction
    with flask_app.app_context():
        BankTransaction.query.delete()
        db.session.commit()
        s, a = _store_with_account(db.session, slug="upsert-store")
        api = _stripe_txn_dict(amount=-1500,
                                description="OFFICE DEPOT")
        row, inserted = upsert_bank_transaction(
            db.session, s.id, a, api,
        )
        assert inserted is True
        assert row.amount_cents == -1500
        assert row.description == "OFFICE DEPOT"
        assert row.stripe_transaction_id == api["id"]


def test_upsert_idempotent_on_existing_id():
    """Same stripe_transaction_id → update existing row, return
    inserted=False."""
    from api.Modules.BankSync.Models import BankTransaction
    from tests._app import app as flask_app, db
    from api.Modules.BankSync.Services import upsert_bank_transaction
    with flask_app.app_context():
        BankTransaction.query.delete()
        db.session.commit()
        s, a = _store_with_account(db.session, slug="upsert-idem")
        api = _stripe_txn_dict()
        row1, inserted1 = upsert_bank_transaction(
            db.session, s.id, a, api,
        )
        # Same id, different description → update.
        api["description"] = "UPDATED DESC"
        row2, inserted2 = upsert_bank_transaction(
            db.session, s.id, a, api,
        )
        assert inserted2 is False
        assert row1.id == row2.id
        assert row2.description == "UPDATED DESC"


def test_upsert_truncates_long_description():
    """description column caps at 500 — defensive truncation."""
    from api.Modules.BankSync.Models import BankTransaction
    from tests._app import app as flask_app, db
    from api.Modules.BankSync.Services import upsert_bank_transaction
    with flask_app.app_context():
        BankTransaction.query.delete()
        db.session.commit()
        s, a = _store_with_account(db.session, slug="upsert-trunc")
        api = _stripe_txn_dict(description="x" * 1000)
        row, _ = upsert_bank_transaction(db.session, s.id, a, api)
        assert len(row.description) == 500


def test_upsert_handles_none_amount():
    """Defensive: None amount → 0 cents, doesn't crash."""
    from api.Modules.BankSync.Models import BankTransaction
    from tests._app import app as flask_app, db
    from api.Modules.BankSync.Services import upsert_bank_transaction
    with flask_app.app_context():
        BankTransaction.query.delete()
        db.session.commit()
        s, a = _store_with_account(db.session, slug="upsert-none-amt")
        api = _stripe_txn_dict(amount=None)
        row, _ = upsert_bank_transaction(db.session, s.id, a, api)
        assert row.amount_cents == 0


# ── backfill_uncategorized_rows ───────────────────────────


def test_backfill_zero_when_no_uncategorized():
    from api.Modules.BankSync.Models import BankTransaction
    from tests._app import app as flask_app, db
    from api.Modules.BankSync.Services import (
        backfill_uncategorized_rows,
    )
    with flask_app.app_context():
        BankTransaction.query.delete()
        db.session.commit()
        s, a = _store_with_account(db.session, slug="backfill-empty")
        # All rows already categorized.
        db.session.add(BankTransaction(
            store_id=s.id, stripe_bank_account_id=a.id,
            stripe_transaction_id="already_tagged",
            amount_cents=-100,
            description="OFFICE",
            category_slug="cash_expense",
        ))
        db.session.commit()
        assert backfill_uncategorized_rows(db.session, s.id) == 0


def test_backfill_tags_uncategorized_via_builtin():
    """An uncategorised REMOTE DEPOSIT FEE on 0230 gets tagged
    by the built-in rule chain on backfill."""
    from api.Modules.BankSync.Models import BankTransaction
    from tests._app import app as flask_app, db
    from api.Modules.BankSync.Services import (
        backfill_uncategorized_rows,
    )
    with flask_app.app_context():
        BankTransaction.query.delete()
        db.session.commit()
        s, a = _store_with_account(db.session, last4="0230")
        db.session.add(BankTransaction(
            store_id=s.id, stripe_bank_account_id=a.id,
            stripe_transaction_id="bf_rdc_1",
            amount_cents=-210,
            description="REMOTE DEPOSIT FEE 04/29",
            category_slug="",
        ))
        db.session.commit()
        tagged = backfill_uncategorized_rows(db.session, s.id)
        assert tagged == 1
        row = BankTransaction.query.filter_by(
            stripe_transaction_id="bf_rdc_1",
        ).first()
        assert row.category_slug == "bank_charge_230"


# ── migrate_generic_bank_charge_per_account ───────────────


def test_migrate_relabels_generic_bank_charge():
    """A row with the legacy `bank_charge` slug + a description
    that matches a current built-in gets retagged to
    `bank_charge_<last4>`."""
    from api.Modules.BankSync.Models import BankTransaction
    from tests._app import app as flask_app, db
    from api.Modules.BankSync.Services import (
        migrate_generic_bank_charge_per_account,
    )
    with flask_app.app_context():
        BankTransaction.query.delete()
        db.session.commit()
        s, a = _store_with_account(db.session, last4="0230")
        db.session.add(BankTransaction(
            store_id=s.id, stripe_bank_account_id=a.id,
            stripe_transaction_id="legacy_charge_1",
            amount_cents=-300,
            description="MSB MONTHLY FEE",
            category_slug="bank_charge",
        ))
        db.session.commit()
        migrated = migrate_generic_bank_charge_per_account(
            db.session, s.id,
        )
        assert migrated == 1
        row = BankTransaction.query.filter_by(
            stripe_transaction_id="legacy_charge_1",
        ).first()
        assert row.category_slug == "bank_charge_230"


def test_migrate_skips_rows_without_matching_builtin_substring():
    """A `bank_charge`-tagged row whose description doesn't match
    any current built-in is treated as an operator override and
    left alone."""
    from api.Modules.BankSync.Models import BankTransaction
    from tests._app import app as flask_app, db
    from api.Modules.BankSync.Services import (
        migrate_generic_bank_charge_per_account,
    )
    with flask_app.app_context():
        BankTransaction.query.delete()
        db.session.commit()
        s, a = _store_with_account(db.session, last4="0230")
        db.session.add(BankTransaction(
            store_id=s.id, stripe_bank_account_id=a.id,
            stripe_transaction_id="manual_override_1",
            amount_cents=-300,
            description="UTILITY BILL",
            category_slug="bank_charge",
        ))
        db.session.commit()
        migrated = migrate_generic_bank_charge_per_account(
            db.session, s.id,
        )
        assert migrated == 0
        row = BankTransaction.query.filter_by(
            stripe_transaction_id="manual_override_1",
        ).first()
        assert row.category_slug == "bank_charge"


def test_migrate_skips_rows_without_account_last4():
    """No last4 → can't build the per-account slug → skip."""
    from api.Modules.BankSync.Models import BankTransaction, StripeBankAccount
    from api.Modules.Tenancy.Models import Store
    from tests._app import app as flask_app, db
    from api.Modules.BankSync.Services import (
        migrate_generic_bank_charge_per_account,
    )
    with flask_app.app_context():
        BankTransaction.query.delete()
        db.session.commit()
        s = Store(name="no-last4", slug="no-last4",
                  plan="basic", email="no-last4@test.com")
        db.session.add(s); db.session.flush()
        a = StripeBankAccount(
            store_id=s.id,
            stripe_account_id="fcacct_no_last4",
            last4="",
            enabled=True,
        )
        db.session.add(a); db.session.flush()
        db.session.add(BankTransaction(
            store_id=s.id, stripe_bank_account_id=a.id,
            stripe_transaction_id="no_last4_charge",
            amount_cents=-100,
            description="MSB MONTHLY FEE",
            category_slug="bank_charge",
        ))
        db.session.commit()
        migrated = migrate_generic_bank_charge_per_account(
            db.session, s.id,
        )
        assert migrated == 0


# ── sync_bank_transactions (orchestrator) ─────────────────


def test_sync_returns_zero_when_stripe_unconfigured(monkeypatch):
    """Stripe disabled → sync no-ops."""
    from tests._app import app as flask_app, db
    from api.Modules.BankSync.Services import sync_bank_transactions
    monkeypatch.delenv("STRIPE_SECRET_KEY", raising=False)
    with flask_app.app_context():
        s, _ = _store_with_account(db.session, slug="no-stripe")
        new_rows, total, err = sync_bank_transactions(db.session, s)
        assert new_rows == 0
        assert total == 0
        assert "Stripe is not configured" in err


def test_sync_iterates_accounts_and_tags_transactions(monkeypatch):
    """Happy path: Stripe configured, one account, two
    transactions (one matching the Nizari built-in, one not).
    Both get inserted; the matching one gets tagged."""
    from api.Modules.BankSync.Models import BankTransaction
    from tests._app import app as flask_app, db
    from api.Modules.BankSync.Services import sync_bank_transactions
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_dummy")
    with flask_app.app_context():
        BankTransaction.query.delete()
        db.session.commit()
        s, a = _store_with_account(db.session, last4="0230")

        # Stub the FC SDK calls.
        api_txns = [
            _stripe_txn_dict(
                description="REMOTE DEPOSIT FEE 04/29",
                amount=-210,
            ),
            _stripe_txn_dict(
                description="MISC TRANSACTION",
                amount=-100,
            ),
        ]
        # auto_paging_iter() returns an iterator of these dicts.
        list_response = MagicMock()
        list_response.auto_paging_iter = MagicMock(
            return_value=iter(api_txns),
        )
        with patch(
            "stripe.financial_connections.Account.subscribe",
        ), patch(
            "stripe.financial_connections.Account.refresh_account",
        ), patch(
            "stripe.financial_connections.Transaction.list",
            return_value=list_response,
        ):
            new_rows, total, err = sync_bank_transactions(db.session, s)
        assert err == ""
        assert new_rows == 2
        assert total == 2
        # Matching txn got tagged.
        rdc = BankTransaction.query.filter(
            BankTransaction.description.like("REMOTE DEPOSIT FEE%"),
        ).first()
        assert rdc.category_slug == "bank_charge_230"
        # Non-matching txn left uncategorised.
        misc = BankTransaction.query.filter_by(
            description="MISC TRANSACTION",
        ).first()
        assert (misc.category_slug or "") == ""


def test_sync_records_account_error_in_last_error(monkeypatch):
    """Stripe API failure on Transaction.list → captured into
    last_error, sync still returns (doesn't crash)."""
    from api.Modules.BankSync.Models import BankTransaction
    from tests._app import app as flask_app, db
    from api.Modules.BankSync.Services import sync_bank_transactions
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_dummy")
    import stripe
    with flask_app.app_context():
        BankTransaction.query.delete()
        db.session.commit()
        s, a = _store_with_account(db.session, slug="err-store")
        # `user_message` is a property without a setter, so we
        # build a StripeError whose str() carries the message;
        # the orchestrator falls back to str(e) when user_message
        # is empty.
        err = stripe.error.StripeError("upstream down")
        with patch(
            "stripe.financial_connections.Account.subscribe",
        ), patch(
            "stripe.financial_connections.Account.refresh_account",
        ), patch(
            "stripe.financial_connections.Transaction.list",
            side_effect=err,
        ):
            new_rows, total, last_error = sync_bank_transactions(
                db.session, s,
            )
        assert new_rows == 0
        assert total == 0
        assert "upstream down" in last_error




