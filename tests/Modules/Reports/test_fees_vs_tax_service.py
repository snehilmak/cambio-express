"""Unit tests for Reports.Services.fees_vs_tax (PR 85)."""
from datetime import date

from app import (
    Store,
    Transfer,
)


_TXN_COUNTER = [0]


def _add_store(db, *, slug="ft-store"):
    s = Store(name=slug, slug=slug, plan="basic",
              email=f"{slug}@example.com")
    db.add(s); db.flush()
    return s


def _add_transfer(db, store_id, *, send_date, fee=2.0,
                   federal_tax=1.0, send_amount=100.0,
                   status="Sent"):
    _TXN_COUNTER[0] += 1
    t = Transfer(
        store_id=store_id,
        send_date=send_date,
        company="Intermex",
        sender_name="x",
        send_amount=send_amount,
        fee=fee,
        federal_tax=federal_tax,
        status=status,
    )
    db.add(t); db.flush()
    return t


# ── empty inputs ──────────────────────────────────────────


def test_empty_store_ids_returns_zero_totals():
    from app import app as flask_app, db
    from api.Modules.Reports.Services import fees_vs_tax
    with flask_app.app_context():
        rows, totals = fees_vs_tax(
            db.session, [],
            date(2026, 5, 1), date(2026, 5, 31),
        )
        assert rows == []
        assert totals == {
            "fees": 0.0, "tax": 0.0, "count": 0, "ratio": 0.0,
        }


def test_no_transfers_returns_zero_totals_with_two_rows():
    """Empty result has 0 totals but the side-by-side rows
    structure is preserved so the template still renders."""
    from app import app as flask_app, db
    from api.Modules.Reports.Services import fees_vs_tax
    with flask_app.app_context():
        Transfer.query.delete()
        db.session.commit()
        s = _add_store(db.session, slug="empty-ft")
        rows, totals = fees_vs_tax(
            db.session, [s.id],
            date(2026, 5, 1), date(2026, 5, 31),
        )
        # Two rows (one for fees, one for tax) even with zero totals.
        assert len(rows) == 2
        assert rows[0]["amount"] == 0.0
        assert rows[1]["amount"] == 0.0
        assert totals == {
            "fees": 0.0, "tax": 0.0, "count": 0, "ratio": 0.0,
        }


# ── happy path ───────────────────────────────────────────


def test_aggregates_fees_and_tax_in_window():
    from app import app as flask_app, db
    from api.Modules.Reports.Services import fees_vs_tax
    with flask_app.app_context():
        Transfer.query.delete()
        db.session.commit()
        s = _add_store(db.session, slug="agg-ft")
        # Three transfers in May, total fee=$15, tax=$6.
        for fee, tax in [(5.0, 2.0), (5.0, 2.0), (5.0, 2.0)]:
            _add_transfer(
                db.session, s.id,
                send_date=date(2026, 5, 15),
                fee=fee, federal_tax=tax,
            )
        rows, totals = fees_vs_tax(
            db.session, [s.id],
            date(2026, 5, 1), date(2026, 5, 31),
        )
        assert totals["fees"] == 15.0
        assert totals["tax"] == 6.0
        assert totals["count"] == 3
        # ratio = 6 / 15 = 0.4
        assert totals["ratio"] == 0.4


def test_rows_order_fees_then_tax():
    """Side-by-side display: fees row first, tax row second."""
    from app import app as flask_app, db
    from api.Modules.Reports.Services import fees_vs_tax
    with flask_app.app_context():
        Transfer.query.delete()
        db.session.commit()
        s = _add_store(db.session, slug="rows-ft")
        _add_transfer(
            db.session, s.id, send_date=date(2026, 5, 1),
            fee=10.0, federal_tax=3.0,
        )
        rows, _ = fees_vs_tax(
            db.session, [s.id],
            date(2026, 5, 1), date(2026, 5, 31),
        )
        assert "Fees" in rows[0]["label"]
        assert "Federal Tax" in rows[1]["label"]
        assert rows[0]["amount"] == 10.0
        assert rows[1]["amount"] == 3.0


def test_excludes_canceled_and_rejected_transfers():
    """Active-period filter excludes Canceled / Rejected."""
    from app import app as flask_app, db
    from api.Modules.Reports.Services import fees_vs_tax
    with flask_app.app_context():
        Transfer.query.delete()
        db.session.commit()
        s = _add_store(db.session, slug="excl-ft")
        d = date(2026, 5, 15)
        _add_transfer(
            db.session, s.id, send_date=d,
            fee=10.0, federal_tax=2.0, status="Sent",
        )
        _add_transfer(
            db.session, s.id, send_date=d,
            fee=99.0, federal_tax=99.0, status="Canceled",
        )
        _add_transfer(
            db.session, s.id, send_date=d,
            fee=99.0, federal_tax=99.0, status="Rejected",
        )
        _, totals = fees_vs_tax(
            db.session, [s.id],
            date(2026, 5, 1), date(2026, 5, 31),
        )
        # Only the Sent transfer should count.
        assert totals["fees"] == 10.0
        assert totals["tax"] == 2.0
        assert totals["count"] == 1


def test_ratio_zero_when_no_fees():
    """ratio = 0.0 (not ZeroDivisionError) when fees total is 0."""
    from app import app as flask_app, db
    from api.Modules.Reports.Services import fees_vs_tax
    with flask_app.app_context():
        Transfer.query.delete()
        db.session.commit()
        s = _add_store(db.session, slug="ratio-zero")
        # Tax with no fee — unusual but defensive.
        _add_transfer(
            db.session, s.id, send_date=date(2026, 5, 1),
            fee=0.0, federal_tax=5.0,
        )
        _, totals = fees_vs_tax(
            db.session, [s.id],
            date(2026, 5, 1), date(2026, 5, 31),
        )
        assert totals["fees"] == 0.0
        assert totals["tax"] == 5.0
        assert totals["ratio"] == 0.0


def test_filters_by_window():
    from app import app as flask_app, db
    from api.Modules.Reports.Services import fees_vs_tax
    with flask_app.app_context():
        Transfer.query.delete()
        db.session.commit()
        s = _add_store(db.session, slug="window-ft")
        # In window
        _add_transfer(
            db.session, s.id, send_date=date(2026, 5, 15),
            fee=10.0, federal_tax=3.0,
        )
        # Outside window
        _add_transfer(
            db.session, s.id, send_date=date(2026, 6, 5),
            fee=99.0, federal_tax=99.0,
        )
        _, totals = fees_vs_tax(
            db.session, [s.id],
            date(2026, 5, 1), date(2026, 5, 31),
        )
        assert totals["fees"] == 10.0
        assert totals["tax"] == 3.0
        assert totals["count"] == 1


def test_filters_by_store_ids():
    from app import app as flask_app, db
    from api.Modules.Reports.Services import fees_vs_tax
    with flask_app.app_context():
        Transfer.query.delete()
        db.session.commit()
        s1 = _add_store(db.session, slug="store-a-ft")
        s2 = _add_store(db.session, slug="store-b-ft")
        _add_transfer(
            db.session, s1.id, send_date=date(2026, 5, 1),
            fee=5.0, federal_tax=1.0,
        )
        _add_transfer(
            db.session, s2.id, send_date=date(2026, 5, 1),
            fee=99.0, federal_tax=99.0,
        )
        _, totals = fees_vs_tax(
            db.session, [s1.id],
            date(2026, 5, 1), date(2026, 5, 31),
        )
        assert totals["fees"] == 5.0
        assert totals["count"] == 1


# ── legacy Flask wrapper ─────────────────────────────────


def test_legacy_fees_vs_tax_data_delegates():
    from app import app as flask_app, db
    from app import _fees_vs_tax_data as legacy
    with flask_app.app_context():
        Transfer.query.delete()
        db.session.commit()
        s = _add_store(db.session, slug="legacy-ft")
        _add_transfer(
            db.session, s.id, send_date=date(2026, 5, 1),
            fee=10.0, federal_tax=2.0,
        )
        rows, totals = legacy(
            [s.id], date(2026, 5, 1), date(2026, 5, 31),
        )
        assert totals["fees"] == 10.0
        assert totals["tax"] == 2.0
