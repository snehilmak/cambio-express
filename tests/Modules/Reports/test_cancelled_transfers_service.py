"""Unit tests for Reports.Services.cancelled_transfers (PR 96)."""
from datetime import date

from api.Modules.Tenancy.Models import Store
from api.Modules.Transfers.Models import Transfer


def _add_store(db, *, slug="ct-store"):
    s = Store(name=slug, slug=slug, plan="basic",
              email=f"{slug}@example.com")
    db.add(s); db.flush()
    return s


def _add_transfer(db, store_id, *, send_date, status="Canceled",
                  send_amount=100.0, sender_name="Sender",
                  recipient_name="Recipient", country="Mexico",
                  company="Intermex", confirm_number="C123",
                  status_notes=""):
    t = Transfer(
        store_id=store_id,
        send_date=send_date,
        company=company,
        sender_name=sender_name,
        recipient_name=recipient_name,
        country=country,
        send_amount=send_amount,
        fee=2.0,
        federal_tax=1.0,
        confirm_number=confirm_number,
        status=status,
        status_notes=status_notes,
    )
    db.add(t); db.flush()
    return t


# ── shape ────────────────────────────────────────────────


def test_returns_rows_and_totals_tuple():
    from tests._app import app as flask_app, db
    from api.Modules.Reports.Services import cancelled_transfers
    with flask_app.app_context():
        Transfer.query.delete()
        db.session.commit()
        s = _add_store(db.session, slug="ct-shape")
        rows, totals = cancelled_transfers(
            db.session, [s.id],
            date(2026, 5, 1), date(2026, 5, 31),
        )
        assert isinstance(rows, list)
        assert set(totals) == {"count", "amount", "canceled", "rejected"}


def test_row_shape():
    from tests._app import app as flask_app, db
    from api.Modules.Reports.Services import cancelled_transfers
    with flask_app.app_context():
        Transfer.query.delete()
        db.session.commit()
        s = _add_store(db.session, slug="ct-row")
        _add_transfer(db.session, s.id,
                      send_date=date(2026, 5, 5),
                      status="Canceled")
        rows, _ = cancelled_transfers(
            db.session, [s.id],
            date(2026, 5, 1), date(2026, 5, 31),
        )
        assert set(rows[0]) == {
            "send_date", "sender_name", "recipient_name",
            "country", "company", "amount", "status",
            "status_notes", "confirm",
        }


# ── status filter ────────────────────────────────────────


def test_active_transfers_excluded():
    """Sent / Pending transfers are NOT in the cancelled list."""
    from tests._app import app as flask_app, db
    from api.Modules.Reports.Services import cancelled_transfers
    with flask_app.app_context():
        Transfer.query.delete()
        db.session.commit()
        s = _add_store(db.session, slug="ct-active")
        _add_transfer(db.session, s.id,
                      send_date=date(2026, 5, 5),
                      status="Sent",
                      send_amount=999.0)
        _add_transfer(db.session, s.id,
                      send_date=date(2026, 5, 6),
                      status="Canceled",
                      send_amount=100.0)
        rows, _ = cancelled_transfers(
            db.session, [s.id],
            date(2026, 5, 1), date(2026, 5, 31),
        )
        assert len(rows) == 1
        assert rows[0]["status"] == "Canceled"


def test_includes_both_canceled_and_rejected():
    """Both Canceled and Rejected statuses surface."""
    from tests._app import app as flask_app, db
    from api.Modules.Reports.Services import cancelled_transfers
    with flask_app.app_context():
        Transfer.query.delete()
        db.session.commit()
        s = _add_store(db.session, slug="ct-both")
        _add_transfer(db.session, s.id,
                      send_date=date(2026, 5, 5),
                      status="Canceled",
                      send_amount=100.0)
        _add_transfer(db.session, s.id,
                      send_date=date(2026, 5, 6),
                      status="Rejected",
                      send_amount=200.0)
        rows, totals = cancelled_transfers(
            db.session, [s.id],
            date(2026, 5, 1), date(2026, 5, 31),
        )
        assert len(rows) == 2
        statuses = {r["status"] for r in rows}
        assert statuses == {"Canceled", "Rejected"}
        assert totals["canceled"] == 1
        assert totals["rejected"] == 1


# ── ordering ─────────────────────────────────────────────


def test_rows_sorted_send_date_descending():
    """Newest send_date first — operator wants the most recent
    cancellations on top."""
    from tests._app import app as flask_app, db
    from api.Modules.Reports.Services import cancelled_transfers
    with flask_app.app_context():
        Transfer.query.delete()
        db.session.commit()
        s = _add_store(db.session, slug="ct-sort")
        _add_transfer(db.session, s.id,
                      send_date=date(2026, 5, 5),
                      status="Canceled",
                      sender_name="oldest")
        _add_transfer(db.session, s.id,
                      send_date=date(2026, 5, 25),
                      status="Canceled",
                      sender_name="newest")
        _add_transfer(db.session, s.id,
                      send_date=date(2026, 5, 15),
                      status="Canceled",
                      sender_name="middle")
        rows, _ = cancelled_transfers(
            db.session, [s.id],
            date(2026, 5, 1), date(2026, 5, 31),
        )
        senders = [r["sender_name"] for r in rows]
        assert senders == ["newest", "middle", "oldest"]


# ── totals ─────────────────────────────────────────────


def test_totals_count_amount_canceled_rejected():
    from tests._app import app as flask_app, db
    from api.Modules.Reports.Services import cancelled_transfers
    with flask_app.app_context():
        Transfer.query.delete()
        db.session.commit()
        s = _add_store(db.session, slug="ct-totals")
        _add_transfer(db.session, s.id,
                      send_date=date(2026, 5, 5),
                      status="Canceled",
                      send_amount=100.0)
        _add_transfer(db.session, s.id,
                      send_date=date(2026, 5, 6),
                      status="Canceled",
                      send_amount=200.0)
        _add_transfer(db.session, s.id,
                      send_date=date(2026, 5, 7),
                      status="Rejected",
                      send_amount=50.0)
        _, totals = cancelled_transfers(
            db.session, [s.id],
            date(2026, 5, 1), date(2026, 5, 31),
        )
        assert totals["count"]    == 3
        assert totals["amount"]   == 350.0
        assert totals["canceled"] == 2
        assert totals["rejected"] == 1


# ── status_notes preserved ───────────────────────────────


def test_status_notes_passed_through():
    """The free-form notes field is exposed verbatim so the
    template can show why a transfer was cancelled."""
    from tests._app import app as flask_app, db
    from api.Modules.Reports.Services import cancelled_transfers
    with flask_app.app_context():
        Transfer.query.delete()
        db.session.commit()
        s = _add_store(db.session, slug="ct-notes")
        _add_transfer(db.session, s.id,
                      send_date=date(2026, 5, 5),
                      status="Rejected",
                      status_notes="OFAC flag — review")
        rows, _ = cancelled_transfers(
            db.session, [s.id],
            date(2026, 5, 1), date(2026, 5, 31),
        )
        assert rows[0]["status_notes"] == "OFAC flag — review"


# ── scoping ─────────────────────────────────────────────


def test_filters_by_store_list():
    from tests._app import app as flask_app, db
    from api.Modules.Reports.Services import cancelled_transfers
    with flask_app.app_context():
        Transfer.query.delete()
        db.session.commit()
        s1 = _add_store(db.session, slug="ct-store-1")
        s2 = _add_store(db.session, slug="ct-store-2")
        _add_transfer(db.session, s1.id,
                      send_date=date(2026, 5, 5),
                      status="Canceled",
                      send_amount=100.0)
        _add_transfer(db.session, s2.id,
                      send_date=date(2026, 5, 5),
                      status="Canceled",
                      send_amount=999.0)
        _, totals = cancelled_transfers(
            db.session, [s1.id],
            date(2026, 5, 1), date(2026, 5, 31),
        )
        assert totals["amount"] == 100.0


def test_filters_by_send_date_window():
    from tests._app import app as flask_app, db
    from api.Modules.Reports.Services import cancelled_transfers
    with flask_app.app_context():
        Transfer.query.delete()
        db.session.commit()
        s = _add_store(db.session, slug="ct-window")
        _add_transfer(db.session, s.id,
                      send_date=date(2026, 4, 30),
                      status="Canceled",
                      send_amount=999.0)
        _add_transfer(db.session, s.id,
                      send_date=date(2026, 5, 15),
                      status="Canceled",
                      send_amount=100.0)
        _, totals = cancelled_transfers(
            db.session, [s.id],
            date(2026, 5, 1), date(2026, 5, 31),
        )
        assert totals["amount"] == 100.0


# ── legacy wrapper ───────────────────────────────────────


