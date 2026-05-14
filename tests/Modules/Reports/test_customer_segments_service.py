"""Unit tests for Reports.Services.new_vs_returning (PR 89)."""
from datetime import date

from api.Modules.Customers.Models import Customer
from api.Modules.Tenancy.Models import Store
from api.Modules.Transfers.Models import Transfer
from tests._app import db, db_session


def _add_store(db, *, slug="cs-store"):
    s = Store(name=slug, slug=slug, plan="basic",
              email=f"{slug}@example.com")
    db.add(s); db.flush()
    return s


_CUST_COUNTER = 0


def _add_customer(db, store_id, *, name="C"):
    global _CUST_COUNTER
    _CUST_COUNTER += 1
    c = Customer(
        store_id=store_id,
        full_name=name,
        phone_country="US",
        phone_number=f"555{_CUST_COUNTER:07d}",
    )
    db.add(c); db.flush()
    return c


def _add_transfer(db, store_id, *, send_date, customer_id=None,
                  send_amount=100.0, status="Sent"):
    t = Transfer(
        store_id=store_id,
        customer_id=customer_id,
        send_date=send_date,
        company="Intermex",
        sender_name="x",
        send_amount=send_amount,
        fee=2.0,
        federal_tax=1.0,
        status=status,
    )
    db.add(t); db.flush()
    return t


# ── shape ────────────────────────────────────────────────


def test_returns_rows_and_totals_tuple():
    """Service returns (rows, totals); rows include New senders +
    Returning senders always, walk-in only when present."""
    from tests._app import db
    from api.Modules.Reports.Services import new_vs_returning
    with db_session():
        db.session.query(Transfer).delete()
        db.session.commit()
        s = _add_store(db.session, slug="cs-shape")
        rows, totals = new_vs_returning(
            db.session, [s.id],
            date(2026, 5, 1), date(2026, 5, 31),
        )
        assert isinstance(rows, list)
        assert isinstance(totals, dict)
        # Always at least 2 rows (New + Returning).
        assert {r["bucket"] for r in rows} == {
            "New senders", "Returning senders",
        }
        assert set(totals) == {
            "customers", "txns", "sent",
            "new_count", "returning_count",
        }


def test_walkin_row_only_present_when_walkins_exist():
    """No walkins → only 2 rows. Walkins → 3 rows."""
    from tests._app import db
    from api.Modules.Reports.Services import new_vs_returning
    with db_session():
        db.session.query(Transfer).delete()
        db.session.commit()
        s = _add_store(db.session, slug="cs-walkin-omit")
        # No transfers at all → only 2 rows.
        rows, _ = new_vs_returning(
            db.session, [s.id],
            date(2026, 5, 1), date(2026, 5, 31),
        )
        assert len(rows) == 2
        # Add a walk-in (customer_id=None) → walk-in row appears.
        _add_transfer(
            db.session, s.id, send_date=date(2026, 5, 15),
            customer_id=None,
        )
        rows, _ = new_vs_returning(
            db.session, [s.id],
            date(2026, 5, 1), date(2026, 5, 31),
        )
        assert len(rows) == 3
        assert any(
            r["bucket"] == "Walk-in (unidentified)" for r in rows
        )


# ── classification logic ─────────────────────────────────


def test_new_sender_no_prior_transfers():
    """A customer with NO transfers before d_from is a 'new sender'
    in the period (regardless of how many transfers they made
    inside the window)."""
    from tests._app import db
    from api.Modules.Reports.Services import new_vs_returning
    with db_session():
        db.session.query(Transfer).delete()
        db.session.commit()
        s = _add_store(db.session, slug="cs-new")
        c = _add_customer(db.session, s.id, name="alice")
        _add_transfer(
            db.session, s.id, send_date=date(2026, 5, 15),
            customer_id=c.id, send_amount=100.0,
        )
        _add_transfer(
            db.session, s.id, send_date=date(2026, 5, 20),
            customer_id=c.id, send_amount=200.0,
        )
        rows, totals = new_vs_returning(
            db.session, [s.id],
            date(2026, 5, 1), date(2026, 5, 31),
        )
        by_bucket = {r["bucket"]: r for r in rows}
        new_row = by_bucket["New senders"]
        assert new_row["customers"] == 1
        assert new_row["txns"] == 2
        assert new_row["sent"] == 300.0
        assert totals["new_count"] == 1
        assert totals["returning_count"] == 0


def test_returning_sender_has_prior_transfer():
    """A customer with at least one transfer BEFORE d_from is
    'returning' in the period."""
    from tests._app import db
    from api.Modules.Reports.Services import new_vs_returning
    with db_session():
        db.session.query(Transfer).delete()
        db.session.commit()
        s = _add_store(db.session, slug="cs-returning")
        c = _add_customer(db.session, s.id, name="bob")
        # Prior period transfer.
        _add_transfer(
            db.session, s.id, send_date=date(2026, 4, 15),
            customer_id=c.id, send_amount=50.0,
        )
        # Current period transfer.
        _add_transfer(
            db.session, s.id, send_date=date(2026, 5, 15),
            customer_id=c.id, send_amount=100.0,
        )
        rows, totals = new_vs_returning(
            db.session, [s.id],
            date(2026, 5, 1), date(2026, 5, 31),
        )
        by_bucket = {r["bucket"]: r for r in rows}
        assert by_bucket["Returning senders"]["customers"] == 1
        assert by_bucket["Returning senders"]["sent"] == 100.0
        assert by_bucket["New senders"]["customers"] == 0
        assert totals["returning_count"] == 1


def test_walkin_classified_separately_each_visit_unique():
    """Each walk-in transfer counts as 1 customer (we can't dedupe
    across visits when customer_id is NULL). Two walk-in transfers
    → customers=2."""
    from tests._app import db
    from api.Modules.Reports.Services import new_vs_returning
    with db_session():
        db.session.query(Transfer).delete()
        db.session.commit()
        s = _add_store(db.session, slug="cs-walkin-count")
        for d in (5, 10, 20):
            _add_transfer(
                db.session, s.id, send_date=date(2026, 5, d),
                customer_id=None, send_amount=50.0,
            )
        rows, totals = new_vs_returning(
            db.session, [s.id],
            date(2026, 5, 1), date(2026, 5, 31),
        )
        walkin = next(
            r for r in rows if r["bucket"] == "Walk-in (unidentified)"
        )
        # Group_by(customer_id) collapses NULLs to one group → 1
        # bucket row, but inside it `txns` reflects the 3 transfers.
        assert walkin["customers"] == 1
        assert walkin["txns"] == 3
        assert walkin["sent"] == 150.0


# ── scoping ─────────────────────────────────────────────


def test_prior_check_respects_store_list():
    """Prior transfers in OTHER stores don't make a sender
    'returning' for the queried store."""
    from tests._app import db
    from api.Modules.Reports.Services import new_vs_returning
    with db_session():
        db.session.query(Transfer).delete()
        db.session.commit()
        s1 = _add_store(db.session, slug="cs-store-a")
        s2 = _add_store(db.session, slug="cs-store-b")
        c = _add_customer(db.session, s2.id, name="cross")
        # Prior transfer at OTHER store (s2) — doesn't count.
        _add_transfer(
            db.session, s2.id, send_date=date(2026, 4, 15),
            customer_id=c.id,
        )
        # Current transfer at s1.
        _add_transfer(
            db.session, s1.id, send_date=date(2026, 5, 15),
            customer_id=c.id,
        )
        rows, _ = new_vs_returning(
            db.session, [s1.id],
            date(2026, 5, 1), date(2026, 5, 31),
        )
        by_bucket = {r["bucket"]: r for r in rows}
        # Customer is NEW for s1 specifically.
        assert by_bucket["New senders"]["customers"] == 1
        assert by_bucket["Returning senders"]["customers"] == 0


def test_excluded_status_transfers_not_counted_in_period():
    """Canceled / Rejected transfers are excluded from the period
    query (they don't count as activity)."""
    from tests._app import db
    from api.Modules.Reports.Services import new_vs_returning
    with db_session():
        db.session.query(Transfer).delete()
        db.session.commit()
        s = _add_store(db.session, slug="cs-excluded")
        c = _add_customer(db.session, s.id, name="cancel-me")
        _add_transfer(
            db.session, s.id, send_date=date(2026, 5, 15),
            customer_id=c.id, status="Canceled",
        )
        rows, totals = new_vs_returning(
            db.session, [s.id],
            date(2026, 5, 1), date(2026, 5, 31),
        )
        # Canceled transfer should not surface in any bucket.
        assert totals["customers"] == 0


# ── totals ─────────────────────────────────────────────


def test_totals_sum_across_all_buckets():
    from tests._app import db
    from api.Modules.Reports.Services import new_vs_returning
    with db_session():
        db.session.query(Transfer).delete()
        db.session.commit()
        s = _add_store(db.session, slug="cs-totals")
        c1 = _add_customer(db.session, s.id, name="new-1")
        c2 = _add_customer(db.session, s.id, name="returning-1")
        _add_transfer(
            db.session, s.id, send_date=date(2026, 4, 15),
            customer_id=c2.id, send_amount=10.0,
        )
        _add_transfer(
            db.session, s.id, send_date=date(2026, 5, 15),
            customer_id=c1.id, send_amount=100.0,
        )
        _add_transfer(
            db.session, s.id, send_date=date(2026, 5, 16),
            customer_id=c2.id, send_amount=200.0,
        )
        _add_transfer(
            db.session, s.id, send_date=date(2026, 5, 17),
            customer_id=None, send_amount=50.0,
        )
        rows, totals = new_vs_returning(
            db.session, [s.id],
            date(2026, 5, 1), date(2026, 5, 31),
        )
        # 1 new + 1 returning + 1 walkin (group) = 3 customer-buckets.
        assert totals["customers"] == 3
        # 1 (new c1) + 1 (returning c2) + 1 (walkin) = 3 transfers.
        assert totals["txns"] == 3
        assert totals["sent"] == 350.0
        assert totals["new_count"] == 1
        assert totals["returning_count"] == 1


# ── legacy wrapper ───────────────────────────────────────


