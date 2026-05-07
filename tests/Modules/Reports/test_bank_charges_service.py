"""Unit tests for Reports.Services.bank_charges (PR 84)."""
from datetime import date, datetime

from app import (
    BankTransaction,
    Store,
    StripeBankAccount,
)


_TXN_COUNTER = [0]
_ACCT_COUNTER = [0]


def _add_store(db, *, slug="bc-store"):
    s = Store(name=slug, slug=slug, plan="basic",
              email=f"{slug}@example.com")
    db.add(s); db.flush()
    return s


def _add_account(db, store_id, *, last4="0210", nickname=None):
    _ACCT_COUNTER[0] += 1
    a = StripeBankAccount(
        store_id=store_id,
        stripe_account_id=f"fcacct_{last4}_{_ACCT_COUNTER[0]}",
        last4=last4,
        nickname=nickname or f"••{last4}",
    )
    db.add(a); db.flush()
    return a


def _add_charge(db, store_id, account_id, *, amount_cents,
                 posted_at, slug="bank_charge"):
    _TXN_COUNTER[0] += 1
    t = BankTransaction(
        store_id=store_id,
        stripe_bank_account_id=account_id,
        stripe_transaction_id=f"txn_bc_{_TXN_COUNTER[0]}",
        amount_cents=amount_cents,
        posted_at=posted_at,
        category_slug=slug,
    )
    db.add(t); db.flush()
    return t


# ── empty inputs ──────────────────────────────────────────


def test_returns_empty_for_no_store_ids():
    from app import app as flask_app, db
    from api.Modules.Reports.Services import bank_charges_by_account
    with flask_app.app_context():
        rows, totals = bank_charges_by_account(
            db.session, [],
            date(2026, 5, 1), date(2026, 5, 31),
        )
        assert rows == []
        assert totals == {"count": 0, "amount": 0.0}


def test_returns_empty_when_no_matching_charges():
    from app import app as flask_app, db
    from api.Modules.Reports.Services import bank_charges_by_account
    with flask_app.app_context():
        BankTransaction.query.delete()
        db.session.commit()
        s = _add_store(db.session, slug="empty-bc")
        rows, totals = bank_charges_by_account(
            db.session, [s.id],
            date(2026, 5, 1), date(2026, 5, 31),
        )
        assert rows == []
        assert totals == {"count": 0, "amount": 0.0}


# ── slug matching ────────────────────────────────────────


def test_includes_legacy_bank_charge_slug():
    """Plain `bank_charge` slug rolls up too (legacy rows)."""
    from app import app as flask_app, db
    from api.Modules.Reports.Services import bank_charges_by_account
    with flask_app.app_context():
        BankTransaction.query.delete()
        db.session.commit()
        s = _add_store(db.session, slug="legacy-slug")
        a = _add_account(db.session, s.id, last4="0210")
        _add_charge(
            db.session, s.id, a.id,
            amount_cents=-100,
            posted_at=datetime(2026, 5, 15),
            slug="bank_charge",
        )
        rows, totals = bank_charges_by_account(
            db.session, [s.id],
            date(2026, 5, 1), date(2026, 5, 31),
        )
        assert len(rows) == 1
        assert rows[0]["amount"] == 1.0
        assert totals["count"] == 1


def test_includes_per_account_bank_charge_slugs():
    """`bank_charge_<last4>` slugs match the prefix."""
    from app import app as flask_app, db
    from api.Modules.Reports.Services import bank_charges_by_account
    with flask_app.app_context():
        BankTransaction.query.delete()
        db.session.commit()
        s = _add_store(db.session, slug="per-acct-slug")
        a = _add_account(db.session, s.id, last4="0230")
        _add_charge(
            db.session, s.id, a.id,
            amount_cents=-210,
            posted_at=datetime(2026, 5, 15),
            slug="bank_charge_230",
        )
        rows, _ = bank_charges_by_account(
            db.session, [s.id],
            date(2026, 5, 1), date(2026, 5, 31),
        )
        assert len(rows) == 1
        assert rows[0]["amount"] == 2.10


def test_excludes_non_bank_charge_slugs():
    """`cash_expense`, `internal_transfer`, etc. don't roll up."""
    from app import app as flask_app, db
    from api.Modules.Reports.Services import bank_charges_by_account
    with flask_app.app_context():
        BankTransaction.query.delete()
        db.session.commit()
        s = _add_store(db.session, slug="non-bc")
        a = _add_account(db.session, s.id)
        _add_charge(
            db.session, s.id, a.id,
            amount_cents=-100,
            posted_at=datetime(2026, 5, 15),
            slug="cash_expense",
        )
        _add_charge(
            db.session, s.id, a.id,
            amount_cents=-200,
            posted_at=datetime(2026, 5, 16),
            slug="internal_transfer",
        )
        rows, totals = bank_charges_by_account(
            db.session, [s.id],
            date(2026, 5, 1), date(2026, 5, 31),
        )
        assert rows == []
        assert totals["count"] == 0


# ── window filtering ─────────────────────────────────────


def test_filters_by_date_window():
    """Charges outside the window are excluded."""
    from app import app as flask_app, db
    from api.Modules.Reports.Services import bank_charges_by_account
    with flask_app.app_context():
        BankTransaction.query.delete()
        db.session.commit()
        s = _add_store(db.session, slug="window-bc")
        a = _add_account(db.session, s.id)
        # In window
        _add_charge(
            db.session, s.id, a.id,
            amount_cents=-100,
            posted_at=datetime(2026, 5, 15),
        )
        # Outside window (next month)
        _add_charge(
            db.session, s.id, a.id,
            amount_cents=-9999,
            posted_at=datetime(2026, 6, 5),
        )
        rows, totals = bank_charges_by_account(
            db.session, [s.id],
            date(2026, 5, 1), date(2026, 5, 31),
        )
        assert len(rows) == 1
        assert totals["amount"] == 1.0


# ── grouping + aggregation ───────────────────────────────


def test_groups_by_account_and_aggregates():
    """Multiple charges on the same account → one row with
    summed amount, count, and computed average."""
    from app import app as flask_app, db
    from api.Modules.Reports.Services import bank_charges_by_account
    with flask_app.app_context():
        BankTransaction.query.delete()
        db.session.commit()
        s = _add_store(db.session, slug="multi-bc")
        a = _add_account(db.session, s.id)
        for amt in (-100, -200, -300):
            _add_charge(
                db.session, s.id, a.id,
                amount_cents=amt,
                posted_at=datetime(2026, 5, 15),
            )
        rows, totals = bank_charges_by_account(
            db.session, [s.id],
            date(2026, 5, 1), date(2026, 5, 31),
        )
        assert len(rows) == 1
        row = rows[0]
        assert row["count"] == 3
        # 1 + 2 + 3 = 6.0
        assert row["amount"] == 6.0
        # avg = 6.0 / 3 = 2.0
        assert row["avg"] == 2.0


def test_separates_rows_by_account():
    """Charges on different accounts produce separate rows."""
    from app import app as flask_app, db
    from api.Modules.Reports.Services import bank_charges_by_account
    with flask_app.app_context():
        BankTransaction.query.delete()
        db.session.commit()
        s = _add_store(db.session, slug="multi-acct-bc")
        a1 = _add_account(db.session, s.id, last4="0210")
        a2 = _add_account(db.session, s.id, last4="0230")
        _add_charge(
            db.session, s.id, a1.id, amount_cents=-100,
            posted_at=datetime(2026, 5, 1),
        )
        _add_charge(
            db.session, s.id, a2.id, amount_cents=-500,
            posted_at=datetime(2026, 5, 2),
        )
        rows, _ = bank_charges_by_account(
            db.session, [s.id],
            date(2026, 5, 1), date(2026, 5, 31),
        )
        assert len(rows) == 2


# ── sort + totals ────────────────────────────────────────


def test_sorts_rows_by_amount_descending():
    """Biggest contributor first."""
    from app import app as flask_app, db
    from api.Modules.Reports.Services import bank_charges_by_account
    with flask_app.app_context():
        BankTransaction.query.delete()
        db.session.commit()
        s = _add_store(db.session, slug="sort-bc")
        a1 = _add_account(db.session, s.id, last4="0210")
        a2 = _add_account(db.session, s.id, last4="0230")
        _add_charge(
            db.session, s.id, a1.id, amount_cents=-100,
            posted_at=datetime(2026, 5, 1),
        )
        _add_charge(
            db.session, s.id, a2.id, amount_cents=-500,
            posted_at=datetime(2026, 5, 2),
        )
        rows, _ = bank_charges_by_account(
            db.session, [s.id],
            date(2026, 5, 1), date(2026, 5, 31),
        )
        # 5.00 row before 1.00 row
        assert rows[0]["amount"] > rows[1]["amount"]


def test_includes_totals_count_and_amount():
    from app import app as flask_app, db
    from api.Modules.Reports.Services import bank_charges_by_account
    with flask_app.app_context():
        BankTransaction.query.delete()
        db.session.commit()
        s = _add_store(db.session, slug="totals-bc")
        a = _add_account(db.session, s.id)
        _add_charge(
            db.session, s.id, a.id, amount_cents=-100,
            posted_at=datetime(2026, 5, 1),
        )
        _add_charge(
            db.session, s.id, a.id, amount_cents=-200,
            posted_at=datetime(2026, 5, 2),
        )
        _, totals = bank_charges_by_account(
            db.session, [s.id],
            date(2026, 5, 1), date(2026, 5, 31),
        )
        assert totals["count"] == 2
        assert totals["amount"] == 3.0


# ── store filter ─────────────────────────────────────────


def test_filters_by_store_ids():
    """Charges in stores not in the filter don't show up."""
    from app import app as flask_app, db
    from api.Modules.Reports.Services import bank_charges_by_account
    with flask_app.app_context():
        BankTransaction.query.delete()
        db.session.commit()
        s1 = _add_store(db.session, slug="filter-s1")
        s2 = _add_store(db.session, slug="filter-s2")
        a1 = _add_account(db.session, s1.id)
        a2 = _add_account(db.session, s2.id)
        _add_charge(
            db.session, s1.id, a1.id, amount_cents=-100,
            posted_at=datetime(2026, 5, 1),
        )
        _add_charge(
            db.session, s2.id, a2.id, amount_cents=-200,
            posted_at=datetime(2026, 5, 1),
        )
        # Filter to s1 only.
        rows, totals = bank_charges_by_account(
            db.session, [s1.id],
            date(2026, 5, 1), date(2026, 5, 31),
        )
        assert totals["count"] == 1
        assert totals["amount"] == 1.0


# ── account-label resolution ──────────────────────────────


def test_uses_account_label_for_display():
    from app import app as flask_app, db
    from api.Modules.Reports.Services import bank_charges_by_account
    with flask_app.app_context():
        BankTransaction.query.delete()
        db.session.commit()
        s = _add_store(db.session, slug="label-bc")
        a = _add_account(
            db.session, s.id, last4="0230",
            nickname="MSB ••0230",
        )
        _add_charge(
            db.session, s.id, a.id, amount_cents=-100,
            posted_at=datetime(2026, 5, 1),
        )
        rows, _ = bank_charges_by_account(
            db.session, [s.id],
            date(2026, 5, 1), date(2026, 5, 31),
        )
        assert rows[0]["account"] == "MSB ••0230"
        assert rows[0]["last4"] == "0230"


# ── legacy Flask wrapper ─────────────────────────────────


def test_legacy_bank_charges_by_account_data_delegates():
    from app import app as flask_app, db
    from app import _bank_charges_by_account_data as legacy
    with flask_app.app_context():
        BankTransaction.query.delete()
        db.session.commit()
        s = _add_store(db.session, slug="legacy-bc")
        a = _add_account(db.session, s.id)
        _add_charge(
            db.session, s.id, a.id, amount_cents=-150,
            posted_at=datetime(2026, 5, 5),
        )
        rows, totals = legacy(
            [s.id], date(2026, 5, 1), date(2026, 5, 31),
        )
        assert len(rows) == 1
        assert totals["amount"] == 1.5
