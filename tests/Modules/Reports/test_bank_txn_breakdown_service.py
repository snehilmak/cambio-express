"""Unit tests for Reports.Services.bank_txn_breakdown (PR 91)."""
from datetime import date, datetime

from app import (
    BankTransaction,
    Store,
    StripeBankAccount,
)


_TXN_COUNTER = 0
_ACCT_COUNTER = 0


def _add_store(db, *, slug="bt-store"):
    s = Store(name=slug, slug=slug, plan="basic",
              email=f"{slug}@example.com")
    db.add(s); db.flush()
    return s


def _add_account(db, store_id, *, last4="1234"):
    global _ACCT_COUNTER
    _ACCT_COUNTER += 1
    a = StripeBankAccount(
        store_id=store_id,
        stripe_account_id=f"fca_test_{_ACCT_COUNTER}",
        last4=last4,
    )
    db.add(a); db.flush()
    return a


def _add_txn(db, store_id, account_id, *, posted_at,
             amount_cents=10000, category_slug=""):
    global _TXN_COUNTER
    _TXN_COUNTER += 1
    t = BankTransaction(
        store_id=store_id,
        stripe_bank_account_id=account_id,
        stripe_transaction_id=f"txn_test_{_TXN_COUNTER}",
        amount_cents=amount_cents,
        posted_at=posted_at,
        status="posted",
        category_slug=category_slug,
    )
    db.add(t); db.flush()
    return t


# ── shape ────────────────────────────────────────────────


def test_returns_rows_and_totals_tuple():
    from app import app as flask_app, db
    from api.Modules.Reports.Services import bank_txn_breakdown
    with flask_app.app_context():
        BankTransaction.query.delete()
        db.session.commit()
        s = _add_store(db.session, slug="bt-shape")
        rows, totals = bank_txn_breakdown(
            db.session, [s.id],
            date(2026, 5, 1), date(2026, 5, 31),
        )
        assert isinstance(rows, list)
        assert isinstance(totals, dict)
        assert set(totals) == {"count", "amount", "inflow", "outflow"}


def test_row_shape():
    from app import app as flask_app, db
    from api.Modules.Reports.Services import bank_txn_breakdown
    with flask_app.app_context():
        BankTransaction.query.delete()
        db.session.commit()
        s = _add_store(db.session, slug="bt-row")
        a = _add_account(db.session, s.id)
        _add_txn(db.session, s.id, a.id,
                 posted_at=datetime(2026, 5, 5),
                 amount_cents=10000,
                 category_slug="bank_charge_210")
        rows, _ = bank_txn_breakdown(
            db.session, [s.id],
            date(2026, 5, 1), date(2026, 5, 31),
        )
        assert len(rows) == 1
        assert set(rows[0]) == {
            "slug", "label", "count", "signed", "amount",
        }


# ── grouping ─────────────────────────────────────────────


def test_groups_by_category_slug():
    from app import app as flask_app, db
    from api.Modules.Reports.Services import bank_txn_breakdown
    with flask_app.app_context():
        BankTransaction.query.delete()
        db.session.commit()
        s = _add_store(db.session, slug="bt-group")
        a = _add_account(db.session, s.id)
        # Two charges in the same bucket.
        _add_txn(db.session, s.id, a.id,
                 posted_at=datetime(2026, 5, 5),
                 amount_cents=-21000,
                 category_slug="bank_charge_210")
        _add_txn(db.session, s.id, a.id,
                 posted_at=datetime(2026, 5, 6),
                 amount_cents=-3300,
                 category_slug="bank_charge_210")
        # One in a different bucket.
        _add_txn(db.session, s.id, a.id,
                 posted_at=datetime(2026, 5, 7),
                 amount_cents=-2000,
                 category_slug="bank_charge_230")
        rows, _ = bank_txn_breakdown(
            db.session, [s.id],
            date(2026, 5, 1), date(2026, 5, 31),
        )
        by_slug = {r["slug"]: r for r in rows}
        assert by_slug["bank_charge_210"]["count"] == 2
        assert by_slug["bank_charge_210"]["amount"] == 243.00
        assert by_slug["bank_charge_230"]["count"] == 1


def test_uncategorised_bucketed_under_empty_slug():
    """Rows with NULL/empty category_slug bucket together."""
    from app import app as flask_app, db
    from api.Modules.Reports.Services import bank_txn_breakdown
    with flask_app.app_context():
        BankTransaction.query.delete()
        db.session.commit()
        s = _add_store(db.session, slug="bt-uncat")
        a = _add_account(db.session, s.id)
        _add_txn(db.session, s.id, a.id,
                 posted_at=datetime(2026, 5, 5),
                 amount_cents=-1000,
                 category_slug="")
        rows, _ = bank_txn_breakdown(
            db.session, [s.id],
            date(2026, 5, 1), date(2026, 5, 31),
        )
        # The "uncategorised" row exists with empty slug.
        empty_row = next(r for r in rows if r["slug"] == "")
        assert empty_row["count"] == 1


# ── inflow / outflow / signed ────────────────────────────


def test_inflow_for_positive_signed_amount():
    """Credit (positive amount_cents) lands in `totals.inflow`."""
    from app import app as flask_app, db
    from api.Modules.Reports.Services import bank_txn_breakdown
    with flask_app.app_context():
        BankTransaction.query.delete()
        db.session.commit()
        s = _add_store(db.session, slug="bt-inflow")
        a = _add_account(db.session, s.id)
        _add_txn(db.session, s.id, a.id,
                 posted_at=datetime(2026, 5, 5),
                 amount_cents=50000,  # +$500
                 category_slug="deposit")
        _, totals = bank_txn_breakdown(
            db.session, [s.id],
            date(2026, 5, 1), date(2026, 5, 31),
        )
        assert totals["inflow"] == 500.0
        assert totals["outflow"] == 0.0
        assert totals["amount"] == 500.0


def test_outflow_for_negative_signed_amount():
    """Debit (negative amount_cents) lands in `totals.outflow`
    as a negative number; absolute lands in `totals.amount`."""
    from app import app as flask_app, db
    from api.Modules.Reports.Services import bank_txn_breakdown
    with flask_app.app_context():
        BankTransaction.query.delete()
        db.session.commit()
        s = _add_store(db.session, slug="bt-outflow")
        a = _add_account(db.session, s.id)
        _add_txn(db.session, s.id, a.id,
                 posted_at=datetime(2026, 5, 5),
                 amount_cents=-50000,  # -$500
                 category_slug="bank_charge_210")
        _, totals = bank_txn_breakdown(
            db.session, [s.id],
            date(2026, 5, 1), date(2026, 5, 31),
        )
        assert totals["inflow"] == 0.0
        assert totals["outflow"] == -500.0
        # `amount` is gross |signed|.
        assert totals["amount"] == 500.0


def test_zero_counted_as_inflow():
    """A 0-cent row (rare but possible — pending hold reversal)
    has signed=0 → falls into inflow side per `signed >= 0`."""
    from app import app as flask_app, db
    from api.Modules.Reports.Services import bank_txn_breakdown
    with flask_app.app_context():
        BankTransaction.query.delete()
        db.session.commit()
        s = _add_store(db.session, slug="bt-zero")
        a = _add_account(db.session, s.id)
        _add_txn(db.session, s.id, a.id,
                 posted_at=datetime(2026, 5, 5),
                 amount_cents=0)
        _, totals = bank_txn_breakdown(
            db.session, [s.id],
            date(2026, 5, 1), date(2026, 5, 31),
        )
        # Zero counted on the inflow side (signed >= 0).
        assert totals["inflow"] == 0.0
        assert totals["outflow"] == 0.0


# ── ordering ─────────────────────────────────────────────


def test_rows_sorted_by_absolute_amount_descending():
    """Biggest |amount| lands first regardless of sign."""
    from app import app as flask_app, db
    from api.Modules.Reports.Services import bank_txn_breakdown
    with flask_app.app_context():
        BankTransaction.query.delete()
        db.session.commit()
        s = _add_store(db.session, slug="bt-sort")
        a = _add_account(db.session, s.id)
        # Small inflow, large outflow.
        _add_txn(db.session, s.id, a.id,
                 posted_at=datetime(2026, 5, 5),
                 amount_cents=1000,
                 category_slug="small_in")
        _add_txn(db.session, s.id, a.id,
                 posted_at=datetime(2026, 5, 6),
                 amount_cents=-99999,
                 category_slug="big_out")
        rows, _ = bank_txn_breakdown(
            db.session, [s.id],
            date(2026, 5, 1), date(2026, 5, 31),
        )
        # big_out (|999.99|) first, small_in ($10.00) second.
        assert rows[0]["slug"] == "big_out"
        assert rows[1]["slug"] == "small_in"


# ── scoping ─────────────────────────────────────────────


def test_filters_by_store_list():
    from app import app as flask_app, db
    from api.Modules.Reports.Services import bank_txn_breakdown
    with flask_app.app_context():
        BankTransaction.query.delete()
        db.session.commit()
        s1 = _add_store(db.session, slug="bt-store-1")
        s2 = _add_store(db.session, slug="bt-store-2")
        a1 = _add_account(db.session, s1.id)
        a2 = _add_account(db.session, s2.id)
        _add_txn(db.session, s1.id, a1.id,
                 posted_at=datetime(2026, 5, 5),
                 amount_cents=10000)
        _add_txn(db.session, s2.id, a2.id,
                 posted_at=datetime(2026, 5, 5),
                 amount_cents=99999)
        _, totals = bank_txn_breakdown(
            db.session, [s1.id],
            date(2026, 5, 1), date(2026, 5, 31),
        )
        assert totals["amount"] == 100.0


def test_filters_by_window_uses_day_boundaries():
    """The window includes posted_at at end-of-day on d_to (so a
    transaction posted at 23:59 on the last day still counts)."""
    from app import app as flask_app, db
    from api.Modules.Reports.Services import bank_txn_breakdown
    with flask_app.app_context():
        BankTransaction.query.delete()
        db.session.commit()
        s = _add_store(db.session, slug="bt-window")
        a = _add_account(db.session, s.id)
        # Late in the last day of the window — still counts.
        _add_txn(db.session, s.id, a.id,
                 posted_at=datetime(2026, 5, 31, 23, 59, 0),
                 amount_cents=10000)
        # Midnight on the day after — excluded.
        _add_txn(db.session, s.id, a.id,
                 posted_at=datetime(2026, 6, 1, 0, 1, 0),
                 amount_cents=99999)
        _, totals = bank_txn_breakdown(
            db.session, [s.id],
            date(2026, 5, 1), date(2026, 5, 31),
        )
        assert totals["amount"] == 100.0


# ── legacy wrapper ───────────────────────────────────────


def test_legacy_wrapper_delegates():
    from app import app as flask_app, db
    from app import _bank_txn_breakdown_data
    from api.Modules.Reports.Services import bank_txn_breakdown
    with flask_app.app_context():
        BankTransaction.query.delete()
        db.session.commit()
        s = _add_store(db.session, slug="bt-legacy")
        a = _add_account(db.session, s.id)
        _add_txn(db.session, s.id, a.id,
                 posted_at=datetime(2026, 5, 5),
                 amount_cents=4200)
        legacy_rows, legacy_totals = _bank_txn_breakdown_data(
            [s.id], date(2026, 5, 1), date(2026, 5, 31),
        )
        svc_rows, svc_totals = bank_txn_breakdown(
            db.session, [s.id],
            date(2026, 5, 1), date(2026, 5, 31),
        )
        assert legacy_rows == svc_rows
        assert legacy_totals == svc_totals
