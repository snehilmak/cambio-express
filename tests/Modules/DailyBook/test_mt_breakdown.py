"""Unit tests for DailyBook.Services.mt_breakdown — per-company
Money Transfer breakdown read + bulk-replace flows."""
from datetime import date, datetime
from tests._app import db


def _add_summary(db, *, store_id, report_date, company, amount=0.0,
                 fees=0.0, federal_tax=0.0, commission=0.0):
    from api.Modules.DailyBook.Models import MoneyTransferSummary
    s = MoneyTransferSummary(
        store_id=store_id, report_date=report_date, company=company,
        amount=amount, fees=fees, federal_tax=federal_tax,
        commission=commission,
    )
    db.add(s); db.flush()
    return s


def _add_transfer(db, *, store_id, send_date, company="Intermex",
                  send_amount=100.0, fee=5.0, federal_tax=1.0,
                  commission=2.0, status="Sent"):
    from api.Modules.Transfers.Models import Transfer
    t = Transfer(
        store_id=store_id, send_date=send_date, company=company,
        service_type="Money Transfer", sender_name="Test",
        send_amount=send_amount, fee=fee, federal_tax=federal_tax,
        commission=commission, status=status,
    )
    db.add(t); db.flush()
    return t


# ── read_mt_breakdown ──────────────────────────────────────


def test_read_empty_day_returns_default_companies(test_store_id):
    """No saved rows, no transfers → one row per configured company
    with both saved + auto = 0."""
    from tests._app import app as flask_app, db
    from api.Modules.DailyBook.Services import read_mt_breakdown
    with flask_app.app_context():
        breakdown = read_mt_breakdown(
            db.session, test_store_id, date.today(),
        )
    companies = [r.company for r in breakdown.rows]
    assert companies == ["Intermex", "Maxi", "Barri"]
    for r in breakdown.rows:
        assert r.saved_amount == 0
        assert r.auto_amount == 0
        assert r.saved_total == 0
        assert r.auto_total == 0
    assert breakdown.saved_total == 0
    assert breakdown.auto_total == 0


def test_read_pulls_auto_from_transfers(test_store_id):
    """A logged transfer surfaces in the row's auto_* fields."""
    from tests._app import app as flask_app, db
    from api.Modules.DailyBook.Services import read_mt_breakdown
    today = date.today()
    with flask_app.app_context():
        _add_transfer(db.session, store_id=test_store_id,
                      send_date=today, company="Intermex",
                      send_amount=200, fee=10, federal_tax=2,
                      commission=3)
        db.session.commit()
        breakdown = read_mt_breakdown(db.session, test_store_id, today)
    intermex = next(r for r in breakdown.rows if r.company == "Intermex")
    assert intermex.auto_count == 1
    assert intermex.auto_amount == 200
    assert intermex.auto_fees == 10
    assert intermex.auto_total == 215  # 200 + 10 + 2 + 3
    # Saved still zero
    assert intermex.saved_total == 0


def test_read_pulls_saved_from_mt_summary(test_store_id):
    """A persisted MoneyTransferSummary row surfaces in saved_*."""
    from tests._app import app as flask_app, db
    from api.Modules.DailyBook.Services import read_mt_breakdown
    today = date.today()
    with flask_app.app_context():
        _add_summary(db.session, store_id=test_store_id,
                     report_date=today, company="Maxi",
                     amount=500, fees=20, federal_tax=5,
                     commission=10)
        db.session.commit()
        breakdown = read_mt_breakdown(db.session, test_store_id, today)
    maxi = next(r for r in breakdown.rows if r.company == "Maxi")
    assert maxi.saved_amount == 500
    assert maxi.saved_total == 535  # 500 + 20 + 5 + 10
    assert maxi.auto_total == 0     # No transfer logged


def test_read_unknown_companies_sort_after_configured(test_store_id):
    """Carry-over companies (saved or logged transfer w/ company
    not in current config) appear after configured, alphabetical."""
    from tests._app import app as flask_app, db
    from api.Modules.DailyBook.Services import read_mt_breakdown
    today = date.today()
    with flask_app.app_context():
        _add_summary(db.session, store_id=test_store_id,
                     report_date=today, company="Zoom",
                     amount=100)
        _add_transfer(db.session, store_id=test_store_id,
                      send_date=today, company="Ria",
                      send_amount=50)
        db.session.commit()
        breakdown = read_mt_breakdown(db.session, test_store_id, today)
    names = [r.company for r in breakdown.rows]
    assert names[:3] == ["Intermex", "Maxi", "Barri"]
    # Both unknowns surface; alphabetical
    assert names[3:] == ["Ria", "Zoom"]


# ── replace_mt_breakdown ───────────────────────────────────


def test_replace_inserts_rows_and_updates_money_transfer(test_store_id):
    """Bulk-replace inserts MT rows + writes the grand total into
    DailyReport.money_transfer."""
    from api.Modules.DailyBook.Models import DailyReport
    from tests._app import app as flask_app, db
    from api.Modules.DailyBook.Services import (
        MTWriteRow,
        read_mt_breakdown,
        replace_mt_breakdown,
    )
    today = date.today()
    with flask_app.app_context():
        total = replace_mt_breakdown(
            db.session,
            store_id=test_store_id,
            report_date=today,
            rows=[
                MTWriteRow(company="Intermex", amount=100, fees=5,
                           federal_tax=1, commission=2),
                MTWriteRow(company="Maxi", amount=200, fees=10,
                           federal_tax=2, commission=3),
            ],
        )
        db.session.commit()
        breakdown = read_mt_breakdown(db.session, test_store_id, today)
        report = (
            db.session.query(DailyReport)
              .filter_by(store_id=test_store_id, report_date=today)
              .first()
        )

    assert total == 323  # 108 + 215
    assert breakdown.saved_total == 323
    assert report.money_transfer == 323

    intermex = next(r for r in breakdown.rows if r.company == "Intermex")
    maxi = next(r for r in breakdown.rows if r.company == "Maxi")
    assert intermex.saved_total == 108
    assert maxi.saved_total == 215


def test_replace_is_bulk_idempotent(test_store_id):
    """Re-calling replace with different rows fully clears the old
    set (no orphaned rows from the previous save)."""
    from api.Modules.DailyBook.Models import MoneyTransferSummary
    from tests._app import app as flask_app, db
    from api.Modules.DailyBook.Services import (
        MTWriteRow,
        replace_mt_breakdown,
    )
    today = date.today()
    with flask_app.app_context():
        replace_mt_breakdown(
            db.session, store_id=test_store_id, report_date=today,
            rows=[
                MTWriteRow(company="Intermex", amount=100, fees=5,
                           federal_tax=1, commission=2),
                MTWriteRow(company="Maxi", amount=200, fees=10,
                           federal_tax=2, commission=3),
            ],
        )
        db.session.commit()
        # Second save drops Maxi entirely
        replace_mt_breakdown(
            db.session, store_id=test_store_id, report_date=today,
            rows=[
                MTWriteRow(company="Intermex", amount=999, fees=0,
                           federal_tax=0, commission=0),
            ],
        )
        db.session.commit()

        rows = (
            db.session.query(MoneyTransferSummary)
              .filter_by(store_id=test_store_id, report_date=today)
              .all()
        )
    by_co = {r.company: r for r in rows}
    assert set(by_co) == {"Intermex"}
    assert by_co["Intermex"].amount == 999


def test_replace_skips_zero_rows(test_store_id):
    """Companies with every-field-zero are not persisted — the
    read-side falls back to auto values for those."""
    from api.Modules.DailyBook.Models import MoneyTransferSummary
    from tests._app import app as flask_app, db
    from api.Modules.DailyBook.Services import (
        MTWriteRow,
        replace_mt_breakdown,
    )
    today = date.today()
    with flask_app.app_context():
        replace_mt_breakdown(
            db.session, store_id=test_store_id, report_date=today,
            rows=[
                MTWriteRow(company="Intermex", amount=0, fees=0,
                           federal_tax=0, commission=0),
                MTWriteRow(company="Maxi", amount=100, fees=0,
                           federal_tax=0, commission=0),
            ],
        )
        db.session.commit()
        rows = (
            db.session.query(MoneyTransferSummary)
              .filter_by(store_id=test_store_id, report_date=today)
              .all()
        )
    # Only Maxi persists
    assert {r.company for r in rows} == {"Maxi"}


def test_replace_refuses_locked_day(test_store_id):
    """Locked day → DailyReportLockedError (the controller surfaces
    as HTTP 403)."""
    import pytest
    from api.Modules.DailyBook.Models import DailyReport
    from tests._app import app as flask_app, db
    from api.Modules.DailyBook.Services import (
        DailyReportLockedError,
        MTWriteRow,
        replace_mt_breakdown,
    )
    today = date.today()
    with flask_app.app_context():
        # Pre-lock the day
        r = DailyReport(
            store_id=test_store_id, report_date=today,
            locked_at=datetime.utcnow(),
        )
        db.session.add(r); db.session.commit()

        with pytest.raises(DailyReportLockedError):
            replace_mt_breakdown(
                db.session, store_id=test_store_id, report_date=today,
                rows=[
                    MTWriteRow(company="Intermex", amount=100,
                               fees=0, federal_tax=0, commission=0),
                ],
            )


def test_replace_empty_rows_preserves_money_transfer(test_store_id):
    """An empty `rows` payload clears every saved row but does NOT
    wipe a manually-typed `money_transfer` on the daily report.
    Use the standard PUT /daily/{store}/{date} endpoint to zero
    that field if the operator really wants to clear it."""
    from api.Modules.DailyBook.Models import DailyReport
    from tests._app import app as flask_app, db
    from api.Modules.DailyBook.Services import (
        MTWriteRow,
        replace_mt_breakdown,
    )
    today = date.today()
    with flask_app.app_context():
        # Seed an existing daily-report with a manual money_transfer
        r = DailyReport(
            store_id=test_store_id, report_date=today,
            money_transfer=500.0,
        )
        db.session.add(r); db.session.commit()

        replace_mt_breakdown(
            db.session, store_id=test_store_id, report_date=today,
            rows=[],
        )
        db.session.commit()

        report = (
            db.session.query(DailyReport)
              .filter_by(store_id=test_store_id, report_date=today)
              .first()
        )
    assert report.money_transfer == 500.0
