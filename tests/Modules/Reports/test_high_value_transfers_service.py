"""Unit tests for Reports.Services.high_value_transfers (PR 93)."""
from datetime import date

from api.Modules.Tenancy.Models import Store
from api.Modules.Transfers.Models import Transfer


def _add_store(db, *, slug="hv-store"):
    s = Store(name=slug, slug=slug, plan="basic",
              email=f"{slug}@example.com")
    db.add(s); db.flush()
    return s


def _add_transfer(db, store_id, *, send_date, send_amount=100.0,
                  fee=2.0, federal_tax=1.0, status="Sent",
                  sender_name="Sender", recipient_name="Recipient",
                  country="Mexico", company="Intermex",
                  confirm_number="C123"):
    t = Transfer(
        store_id=store_id,
        send_date=send_date,
        company=company,
        sender_name=sender_name,
        recipient_name=recipient_name,
        country=country,
        send_amount=send_amount,
        fee=fee,
        federal_tax=federal_tax,
        confirm_number=confirm_number,
        status=status,
    )
    db.add(t); db.flush()
    return t


# ── shape ────────────────────────────────────────────────


def test_returns_rows_and_totals_tuple():
    from app import app as flask_app, db
    from api.Modules.Reports.Services import high_value_transfers
    with flask_app.app_context():
        Transfer.query.delete()
        db.session.commit()
        s = _add_store(db.session, slug="hv-shape")
        rows, totals = high_value_transfers(
            db.session, [s.id],
            date(2026, 5, 1), date(2026, 5, 31),
            threshold=3000.0,
        )
        assert isinstance(rows, list)
        assert isinstance(totals, dict)
        assert set(totals) == {"count", "amount", "fees", "tax"}


def test_row_shape():
    from app import app as flask_app, db
    from api.Modules.Reports.Services import high_value_transfers
    with flask_app.app_context():
        Transfer.query.delete()
        db.session.commit()
        s = _add_store(db.session, slug="hv-row")
        _add_transfer(db.session, s.id,
                      send_date=date(2026, 5, 5),
                      send_amount=5000.0)
        rows, _ = high_value_transfers(
            db.session, [s.id],
            date(2026, 5, 1), date(2026, 5, 31),
            threshold=3000.0,
        )
        assert len(rows) == 1
        assert set(rows[0]) == {
            "send_date", "sender_name", "recipient_name",
            "country", "company", "amount", "fee", "tax",
            "confirm",
        }


# ── threshold filter ─────────────────────────────────────


def test_below_threshold_excluded():
    """Transfer below threshold is not in rows."""
    from app import app as flask_app, db
    from api.Modules.Reports.Services import high_value_transfers
    with flask_app.app_context():
        Transfer.query.delete()
        db.session.commit()
        s = _add_store(db.session, slug="hv-below")
        _add_transfer(db.session, s.id,
                      send_date=date(2026, 5, 5),
                      send_amount=2999.99)
        _add_transfer(db.session, s.id,
                      send_date=date(2026, 5, 6),
                      send_amount=3000.0)
        rows, _ = high_value_transfers(
            db.session, [s.id],
            date(2026, 5, 1), date(2026, 5, 31),
            threshold=3000.0,
        )
        # Only the >= 3000 row should appear.
        assert len(rows) == 1
        assert rows[0]["amount"] == 3000.0


def test_threshold_inclusive_at_exact_value():
    """`send_amount == threshold` is included (it's `>=`)."""
    from app import app as flask_app, db
    from api.Modules.Reports.Services import high_value_transfers
    with flask_app.app_context():
        Transfer.query.delete()
        db.session.commit()
        s = _add_store(db.session, slug="hv-equal")
        _add_transfer(db.session, s.id,
                      send_date=date(2026, 5, 5),
                      send_amount=5000.0)
        rows, _ = high_value_transfers(
            db.session, [s.id],
            date(2026, 5, 1), date(2026, 5, 31),
            threshold=5000.0,
        )
        assert len(rows) == 1


# ── ordering ─────────────────────────────────────────────


def test_rows_sorted_by_amount_descending_then_date():
    from app import app as flask_app, db
    from api.Modules.Reports.Services import high_value_transfers
    with flask_app.app_context():
        Transfer.query.delete()
        db.session.commit()
        s = _add_store(db.session, slug="hv-sort")
        _add_transfer(db.session, s.id,
                      send_date=date(2026, 5, 5),
                      send_amount=5000.0,
                      sender_name="medium")
        _add_transfer(db.session, s.id,
                      send_date=date(2026, 5, 6),
                      send_amount=10000.0,
                      sender_name="big")
        _add_transfer(db.session, s.id,
                      send_date=date(2026, 5, 7),
                      send_amount=3001.0,
                      sender_name="small")
        rows, _ = high_value_transfers(
            db.session, [s.id],
            date(2026, 5, 1), date(2026, 5, 31),
            threshold=3000.0,
        )
        senders = [r["sender_name"] for r in rows]
        assert senders == ["big", "medium", "small"]


# ── totals ─────────────────────────────────────────────


def test_totals_sum_amount_fee_tax():
    from app import app as flask_app, db
    from api.Modules.Reports.Services import high_value_transfers
    with flask_app.app_context():
        Transfer.query.delete()
        db.session.commit()
        s = _add_store(db.session, slug="hv-totals")
        _add_transfer(db.session, s.id,
                      send_date=date(2026, 5, 5),
                      send_amount=5000.0, fee=10.0,
                      federal_tax=5.0)
        _add_transfer(db.session, s.id,
                      send_date=date(2026, 5, 6),
                      send_amount=3000.0, fee=8.0,
                      federal_tax=4.0)
        _, totals = high_value_transfers(
            db.session, [s.id],
            date(2026, 5, 1), date(2026, 5, 31),
            threshold=3000.0,
        )
        assert totals["count"]  == 2
        assert totals["amount"] == 8000.0
        assert totals["fees"]   == 18.0
        assert totals["tax"]    == 9.0


# ── scoping ─────────────────────────────────────────────


def test_excluded_status_transfers_not_listed():
    """Cancelled / refunded transfers don't appear in HV — they're
    not active-period transfers."""
    from app import app as flask_app, db
    from api.Modules.Reports.Services import high_value_transfers
    with flask_app.app_context():
        Transfer.query.delete()
        db.session.commit()
        s = _add_store(db.session, slug="hv-canceled")
        _add_transfer(db.session, s.id,
                      send_date=date(2026, 5, 5),
                      send_amount=5000.0,
                      status="Canceled")
        rows, _ = high_value_transfers(
            db.session, [s.id],
            date(2026, 5, 1), date(2026, 5, 31),
            threshold=3000.0,
        )
        assert rows == []


def test_filters_by_store_list():
    from app import app as flask_app, db
    from api.Modules.Reports.Services import high_value_transfers
    with flask_app.app_context():
        Transfer.query.delete()
        db.session.commit()
        s1 = _add_store(db.session, slug="hv-store-1")
        s2 = _add_store(db.session, slug="hv-store-2")
        _add_transfer(db.session, s1.id,
                      send_date=date(2026, 5, 5),
                      send_amount=5000.0)
        _add_transfer(db.session, s2.id,
                      send_date=date(2026, 5, 5),
                      send_amount=5000.0)
        rows, _ = high_value_transfers(
            db.session, [s1.id],
            date(2026, 5, 1), date(2026, 5, 31),
            threshold=3000.0,
        )
        assert len(rows) == 1


# ── empty ────────────────────────────────────────────────


def test_empty_window_returns_empty_rows_and_zero_totals():
    from app import app as flask_app, db
    from api.Modules.Reports.Services import high_value_transfers
    with flask_app.app_context():
        Transfer.query.delete()
        db.session.commit()
        s = _add_store(db.session, slug="hv-empty")
        rows, totals = high_value_transfers(
            db.session, [s.id],
            date(2026, 5, 1), date(2026, 5, 31),
            threshold=3000.0,
        )
        assert rows == []
        assert totals == {"count": 0, "amount": 0.0,
                          "fees": 0.0, "tax": 0.0}


# ── legacy wrapper ───────────────────────────────────────


