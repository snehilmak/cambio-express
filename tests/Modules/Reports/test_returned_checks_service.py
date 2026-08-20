"""Unit tests for Reports.Services.returned_check_status (PR 90)."""
from datetime import date

from api.Modules.ReturnChecks.Models import ReturnCheck, ReturnCheckPayment
from api.Modules.Tenancy.Models import Store
from tests._app import db, db_session


def _add_store(db, *, slug="rc-store"):
    s = Store(name=slug, slug=slug, plan="basic",
              email=f"{slug}@example.com")
    db.add(s); db.flush()
    return s


def _add_rc(db, store_id, *, bounced_on, status="pending",
            amount=100.0, customer_name="X"):
    r = ReturnCheck(
        store_id=store_id,
        bounced_on=bounced_on,
        customer_name=customer_name,
        amount=amount,
        status=status,
    )
    db.add(r); db.flush()
    return r


def _add_payment(db, rc_id, *, amount, paid_on):
    p = ReturnCheckPayment(
        return_check_id=rc_id,
        amount=amount,
        paid_on=paid_on,
    )
    db.add(p); db.flush()
    return p


# ── shape ────────────────────────────────────────────────


def test_returns_rows_and_totals_tuple():
    """Service returns (rows, totals) with consistent shapes."""
    from tests._app import db
    from api.Modules.Reports.Services import returned_check_status
    with db_session():
        db.session.query(ReturnCheck).delete()
        db.session.commit()
        s = _add_store(db.session, slug="rc-shape")
        rows, totals = returned_check_status(
            db.session, [s.id],
            date(2026, 5, 1), date(2026, 5, 31),
        )
        assert isinstance(rows, list)
        assert isinstance(totals, dict)
        assert set(totals) == {
            "count", "amount", "recovered", "loss_fraud", "net_gl",
        }


def test_empty_buckets_skipped_in_rows():
    """Statuses with 0 count are NOT emitted as a row — keeps the
    template from rendering zero-value cards."""
    from tests._app import db
    from api.Modules.Reports.Services import returned_check_status
    with db_session():
        db.session.query(ReturnCheck).delete()
        db.session.commit()
        s = _add_store(db.session, slug="rc-empty")
        # Only pending checks — no loss / recovered / fraud.
        _add_rc(db.session, s.id,
                bounced_on=date(2026, 5, 5), status="pending")
        rows, _ = returned_check_status(
            db.session, [s.id],
            date(2026, 5, 1), date(2026, 5, 31),
        )
        # Exactly one row for "pending"; no zero rows for others.
        assert len(rows) == 1
        assert rows[0]["status_key"] == "pending"


# ── ordering ─────────────────────────────────────────────


def test_rows_sorted_in_fixed_display_order():
    """Display order is pending → recovered → loss → fraud,
    even when DB returns them differently."""
    from tests._app import db
    from api.Modules.Reports.Services import returned_check_status
    with db_session():
        db.session.query(ReturnCheck).delete()
        db.session.commit()
        s = _add_store(db.session, slug="rc-order")
        # Insert in scrambled order.
        _add_rc(db.session, s.id,
                bounced_on=date(2026, 5, 1), status="loss")
        _add_rc(db.session, s.id,
                bounced_on=date(2026, 5, 2), status="fraud")
        _add_rc(db.session, s.id,
                bounced_on=date(2026, 5, 3), status="pending")
        _add_rc(db.session, s.id,
                bounced_on=date(2026, 5, 4), status="recovered")
        rows, _ = returned_check_status(
            db.session, [s.id],
            date(2026, 5, 1), date(2026, 5, 31),
        )
        keys = [r["status_key"] for r in rows]
        assert keys == ["pending", "recovered", "loss", "fraud"]


# ── recovered amount sourcing ────────────────────────────


def test_recovered_counts_payments_on_pending_rows():
    """`recovered` reflects real money back on EVERY status —
    a pending check with installments already paid must show those
    dollars, not $0 (user-reported bug: full payback + fee showed
    Recovered $0.00 while the row still sat in pending)."""
    from tests._app import db
    from api.Modules.Reports.Services import returned_check_status
    with db_session():
        db.session.query(ReturnCheck).delete()
        db.session.commit()
        s = _add_store(db.session, slug="rc-rec-non")
        rc = _add_rc(db.session, s.id,
                     bounced_on=date(2026, 5, 5),
                     status="pending", amount=100.0)
        _add_payment(db.session, rc.id, amount=30.0,
                     paid_on=date(2026, 5, 10))
        rows, totals = returned_check_status(
            db.session, [s.id],
            date(2026, 5, 1), date(2026, 5, 31),
        )
        pending = next(r for r in rows if r["status_key"] == "pending")
        assert pending["recovered"] == 30.0
        assert totals["recovered"] == 30.0
        assert totals["net_gl"] == 30.0


def test_recovered_includes_bounce_fee_payments():
    """Payments pay down face amount + the bounce fee (total_due),
    so a fully-collected check shows amount + fee as recovered —
    the user's case: $1,000 check + $35 fee → $1,035 back."""
    from tests._app import db
    from api.Modules.Reports.Services import returned_check_status
    with db_session():
        db.session.query(ReturnCheck).delete()
        db.session.commit()
        s = _add_store(db.session, slug="rc-rec-fee")
        rc = _add_rc(db.session, s.id,
                     bounced_on=date(2026, 6, 5),
                     status="pending", amount=1000.0)
        rc.return_check_fee = 35.0
        _add_payment(db.session, rc.id, amount=1000.0,
                     paid_on=date(2026, 6, 10))
        _add_payment(db.session, rc.id, amount=35.0,
                     paid_on=date(2026, 6, 12))
        rows, totals = returned_check_status(
            db.session, [s.id],
            date(2026, 6, 1), date(2026, 6, 30),
        )
        pending = next(r for r in rows if r["status_key"] == "pending")
        assert pending["recovered"] == 1035.0
        assert totals["recovered"] == 1035.0


def test_recovered_sums_payment_rows_for_recovered_status():
    """For a recovered check, `recovered` = Σ payment amounts."""
    from tests._app import db
    from api.Modules.Reports.Services import returned_check_status
    with db_session():
        db.session.query(ReturnCheck).delete()
        db.session.commit()
        s = _add_store(db.session, slug="rc-rec-sum")
        rc = _add_rc(db.session, s.id,
                     bounced_on=date(2026, 5, 5),
                     status="recovered", amount=300.0)
        _add_payment(db.session, rc.id, amount=200.0,
                     paid_on=date(2026, 5, 10))
        _add_payment(db.session, rc.id, amount=100.0,
                     paid_on=date(2026, 5, 15))
        rows, totals = returned_check_status(
            db.session, [s.id],
            date(2026, 5, 1), date(2026, 5, 31),
        )
        recovered = next(
            r for r in rows if r["status_key"] == "recovered"
        )
        assert recovered["recovered"] == 300.0
        assert totals["recovered"] == 300.0


# ── totals ─────────────────────────────────────────────


def test_loss_fraud_combined_in_totals():
    """`loss_fraud` total combines the amounts of loss + fraud."""
    from tests._app import db
    from api.Modules.Reports.Services import returned_check_status
    with db_session():
        db.session.query(ReturnCheck).delete()
        db.session.commit()
        s = _add_store(db.session, slug="rc-loss-fraud")
        _add_rc(db.session, s.id,
                bounced_on=date(2026, 5, 5),
                status="loss", amount=100.0)
        _add_rc(db.session, s.id,
                bounced_on=date(2026, 5, 6),
                status="fraud", amount=50.0)
        _, totals = returned_check_status(
            db.session, [s.id],
            date(2026, 5, 1), date(2026, 5, 31),
        )
        assert totals["loss_fraud"] == 150.0


def test_net_gl_is_recovered_minus_loss_fraud():
    """net_gl is the headline P&L line: recoveries beat write-offs."""
    from tests._app import db
    from api.Modules.Reports.Services import returned_check_status
    with db_session():
        db.session.query(ReturnCheck).delete()
        db.session.commit()
        s = _add_store(db.session, slug="rc-netgl")
        rc = _add_rc(db.session, s.id,
                     bounced_on=date(2026, 5, 5),
                     status="recovered", amount=200.0)
        _add_payment(db.session, rc.id, amount=200.0,
                     paid_on=date(2026, 5, 10))
        _add_rc(db.session, s.id,
                bounced_on=date(2026, 5, 6),
                status="loss", amount=80.0)
        _, totals = returned_check_status(
            db.session, [s.id],
            date(2026, 5, 1), date(2026, 5, 31),
        )
        assert totals["recovered"] == 200.0
        assert totals["loss_fraud"] == 80.0
        assert totals["net_gl"] == 120.0


def test_count_amount_totals_sum_all_buckets():
    from tests._app import db
    from api.Modules.Reports.Services import returned_check_status
    with db_session():
        db.session.query(ReturnCheck).delete()
        db.session.commit()
        s = _add_store(db.session, slug="rc-counts")
        _add_rc(db.session, s.id,
                bounced_on=date(2026, 5, 5),
                status="pending", amount=100.0)
        _add_rc(db.session, s.id,
                bounced_on=date(2026, 5, 6),
                status="loss", amount=50.0)
        _, totals = returned_check_status(
            db.session, [s.id],
            date(2026, 5, 1), date(2026, 5, 31),
        )
        assert totals["count"] == 2
        assert totals["amount"] == 150.0


# ── scoping ─────────────────────────────────────────────


def test_filters_by_store_list():
    from tests._app import db
    from api.Modules.Reports.Services import returned_check_status
    with db_session():
        db.session.query(ReturnCheck).delete()
        db.session.commit()
        s1 = _add_store(db.session, slug="rc-store-1")
        s2 = _add_store(db.session, slug="rc-store-2")
        _add_rc(db.session, s1.id,
                bounced_on=date(2026, 5, 5),
                status="pending", amount=100.0)
        _add_rc(db.session, s2.id,
                bounced_on=date(2026, 5, 5),
                status="pending", amount=999.0)
        _, totals = returned_check_status(
            db.session, [s1.id],
            date(2026, 5, 1), date(2026, 5, 31),
        )
        assert totals["amount"] == 100.0


def test_filters_by_bounced_on_window():
    """bounced_on filter respects [d_from, d_to]."""
    from tests._app import db
    from api.Modules.Reports.Services import returned_check_status
    with db_session():
        db.session.query(ReturnCheck).delete()
        db.session.commit()
        s = _add_store(db.session, slug="rc-window")
        _add_rc(db.session, s.id,
                bounced_on=date(2026, 4, 30),
                status="pending", amount=999.0)
        _add_rc(db.session, s.id,
                bounced_on=date(2026, 6, 1),
                status="pending", amount=999.0)
        _add_rc(db.session, s.id,
                bounced_on=date(2026, 5, 15),
                status="pending", amount=100.0)
        _, totals = returned_check_status(
            db.session, [s.id],
            date(2026, 5, 1), date(2026, 5, 31),
        )
        assert totals["amount"] == 100.0


# ── legacy wrapper ───────────────────────────────────────


