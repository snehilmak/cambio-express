"""Unit tests for BankSync.Services.charges (PR 57)."""
from datetime import datetime


_TXN_COUNTER = [0]


def _ensure_account(db, store_id):
    """Ensure a default StripeBankAccount exists for this store and
    return it. BankTransaction.stripe_bank_account_id is NOT NULL,
    so every test row needs a parent account row."""
    from api.Modules.BankSync.Models import StripeBankAccount
    existing = StripeBankAccount.query.filter_by(store_id=store_id).first()
    if existing is not None:
        return existing
    a = StripeBankAccount(
        store_id=store_id,
        stripe_account_id=f"fcacct_default_{store_id}",
        last4="0000",
    )
    db.add(a)
    db.flush()
    return a


def _add_txn(db, store_id, *, amount_cents, posted_at, slug,
             description="REMOTE DEPOSIT FEE", account_id=None):
    from api.Modules.BankSync.Models import BankTransaction
    if account_id is None:
        account_id = _ensure_account(db, store_id).id
    _TXN_COUNTER[0] += 1
    t = BankTransaction(
        store_id=store_id,
        stripe_bank_account_id=account_id,
        stripe_transaction_id=f"txn_test_{_TXN_COUNTER[0]}",
        amount_cents=amount_cents,
        posted_at=posted_at,
        category_slug=slug,
        description=description,
    )
    db.add(t)
    db.flush()
    return t


def _make_account(db, store_id, *, last4="0230", nickname="MSB ••0230"):
    from api.Modules.BankSync.Models import StripeBankAccount
    a = StripeBankAccount(
        store_id=store_id,
        stripe_account_id=f"fcacct_{last4}",
        last4=last4,
        nickname=nickname,
    )
    db.add(a)
    db.flush()
    return a


# ── bank_charges_for_month ─────────────────────────────────


def test_for_month_sums_exact_slug_match(test_store_id):
    from app import app as flask_app, db
    from api.Modules.BankSync.Services import bank_charges_for_month
    with flask_app.app_context():
        _add_txn(db.session, test_store_id,
                 amount_cents=-210, posted_at=datetime(2026, 5, 15),
                 slug="bank_charge_230")
        result = bank_charges_for_month(
            db.session, test_store_id, 2026, 5,
            category_slug="bank_charge_230",
        )
        # Stored as -210 cents; expense is positive 2.10 dollars.
        assert result == 2.10


def test_for_month_returns_zero_when_no_matches(test_store_id):
    from app import app as flask_app, db
    from api.Modules.BankSync.Services import bank_charges_for_month
    with flask_app.app_context():
        result = bank_charges_for_month(
            db.session, test_store_id, 2026, 5,
            category_slug="bank_charge_230",
        )
        assert result == 0.0


def test_for_month_filters_by_window(test_store_id):
    """Transactions outside the month don't count."""
    from app import app as flask_app, db
    from api.Modules.BankSync.Services import bank_charges_for_month
    with flask_app.app_context():
        # In window
        _add_txn(db.session, test_store_id,
                 amount_cents=-300, posted_at=datetime(2026, 5, 15),
                 slug="bank_charge_230")
        # Outside window (different month)
        _add_txn(db.session, test_store_id,
                 amount_cents=-1000, posted_at=datetime(2026, 4, 30),
                 slug="bank_charge_230")
        # Outside window (different year)
        _add_txn(db.session, test_store_id,
                 amount_cents=-2000, posted_at=datetime(2025, 5, 15),
                 slug="bank_charge_230")
        result = bank_charges_for_month(
            db.session, test_store_id, 2026, 5,
            category_slug="bank_charge_230",
        )
        assert result == 3.0


def test_for_month_prefix_match_rolls_up(test_store_id):
    """Prefix mode: bank_charge / bank_charge_210 / bank_charge_230
    all roll into bank_charges_total."""
    from app import app as flask_app, db
    from api.Modules.BankSync.Services import bank_charges_for_month
    with flask_app.app_context():
        _add_txn(db.session, test_store_id,
                 amount_cents=-100, posted_at=datetime(2026, 5, 1),
                 slug="bank_charge")
        _add_txn(db.session, test_store_id,
                 amount_cents=-210, posted_at=datetime(2026, 5, 5),
                 slug="bank_charge_210")
        _add_txn(db.session, test_store_id,
                 amount_cents=-300, posted_at=datetime(2026, 5, 10),
                 slug="bank_charge_230")
        result = bank_charges_for_month(
            db.session, test_store_id, 2026, 5, prefix="bank_charge",
        )
        # 1.00 + 2.10 + 3.00 = 6.10
        assert result == 6.10


def test_for_month_filters_by_store(test_store_id):
    """Transactions in another store don't count."""
    from api.Modules.Tenancy.Models import Store
    from app import app as flask_app, db
    from api.Modules.BankSync.Services import bank_charges_for_month
    with flask_app.app_context():
        # Create a second store + a charge for it.
        other = Store(name="Other", slug="other-store",
                      plan="basic", email="other@test.com")
        db.session.add(other)
        db.session.flush()
        _add_txn(db.session, other.id,
                 amount_cents=-9999, posted_at=datetime(2026, 5, 15),
                 slug="bank_charge_230")
        # Sum for test_store_id stays 0.
        result = bank_charges_for_month(
            db.session, test_store_id, 2026, 5,
            category_slug="bank_charge_230",
        )
        assert result == 0.0


# ── bank_charges_breakdown_for_month ───────────────────────


def test_breakdown_returns_empty_when_no_rows(test_store_id):
    from app import app as flask_app, db
    from api.Modules.BankSync.Services import (
        bank_charges_breakdown_for_month,
    )
    with flask_app.app_context():
        result = bank_charges_breakdown_for_month(
            db.session, test_store_id, 2026, 5,
        )
        assert result == []


def test_breakdown_groups_by_description(test_store_id):
    from app import app as flask_app, db
    from api.Modules.BankSync.Services import (
        bank_charges_breakdown_for_month,
    )
    with flask_app.app_context():
        _add_txn(db.session, test_store_id,
                 amount_cents=-100, posted_at=datetime(2026, 5, 1),
                 slug="bank_charge_230",
                 description="REMOTE DEPOSIT FEE")
        _add_txn(db.session, test_store_id,
                 amount_cents=-210, posted_at=datetime(2026, 5, 5),
                 slug="bank_charge_230",
                 description="REMOTE DEPOSIT FEE")
        _add_txn(db.session, test_store_id,
                 amount_cents=-500, posted_at=datetime(2026, 5, 8),
                 slug="bank_charge_210",
                 description="WIRE FEE")
        result = bank_charges_breakdown_for_month(
            db.session, test_store_id, 2026, 5,
        )
        assert len(result) == 2
        # Sorted by total desc; WIRE FEE (5.00) outranks
        # REMOTE DEPOSIT FEE (3.10).
        assert result[0]["description"] == "WIRE FEE"
        assert result[0]["total"] == 5.0
        assert result[0]["count"] == 1
        assert result[1]["description"] == "REMOTE DEPOSIT FEE"
        assert result[1]["total"] == 3.10
        assert result[1]["count"] == 2


def test_breakdown_includes_account_label_via_join(test_store_id):
    from app import app as flask_app, db
    from api.Modules.BankSync.Services import (
        bank_charges_breakdown_for_month,
    )
    with flask_app.app_context():
        acct = _make_account(db.session, test_store_id, last4="0230",
                              nickname="MSB ••0230")
        _add_txn(db.session, test_store_id,
                 amount_cents=-210, posted_at=datetime(2026, 5, 1),
                 slug="bank_charge_230", account_id=acct.id)
        result = bank_charges_breakdown_for_month(
            db.session, test_store_id, 2026, 5,
        )
        assert len(result) == 1
        assert result[0]["transactions"][0]["account_label"] == "MSB ••0230"


def test_breakdown_handles_missing_description_with_placeholder(test_store_id):
    from app import app as flask_app, db
    from api.Modules.BankSync.Services import (
        bank_charges_breakdown_for_month,
    )
    with flask_app.app_context():
        _add_txn(db.session, test_store_id,
                 amount_cents=-100, posted_at=datetime(2026, 5, 1),
                 slug="bank_charge_230",
                 description="")
        result = bank_charges_breakdown_for_month(
            db.session, test_store_id, 2026, 5,
        )
        assert result[0]["description"] == "(no description)"


# ── legacy Flask wrappers ──────────────────────────────────


def test_legacy_for_month_delegates(test_store_id):
    from app import app as flask_app, db
    from app import _bank_charges_for_month as legacy
    with flask_app.app_context():
        _add_txn(db.session, test_store_id,
                 amount_cents=-210, posted_at=datetime(2026, 5, 15),
                 slug="bank_charge_230")
        assert legacy(test_store_id, 2026, 5,
                      category_slug="bank_charge_230") == 2.10


