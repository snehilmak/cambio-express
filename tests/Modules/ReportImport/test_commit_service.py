"""Unit tests for commit_intermex_to_mt_breakdown — aggregating a
parsed Intermex report into the day's money-transfer breakdown."""
from datetime import date

import pytest

from tests._app import db, db_session


def _giro(num, send, fee, tax, *, cancelled=False):
    from api.Modules.ReportImport.Services import IntermexTxnRow
    return IntermexTxnRow(
        section="giros", confirm_number=num,
        send_amount=send, fee=fee, federal_tax=tax,
        total_collected=round(send + fee + tax, 2), cashier="CASH",
        cancelled=cancelled, replacement=False, reconciles=True,
    )


def _report(giros):
    # giros_totals=None → all_reconcile keys purely off the per-row
    # reconciles flags (no stated-total cross-check needed here).
    from api.Modules.ReportImport.Services import IntermexDailyReport
    return IntermexDailyReport(
        agency="TEST", report_date=date(2026, 5, 1),
        giros=giros, money_orders=[], bill_payments=[],
    )


def _add_summary(store_id, day, company, **kw):
    from api.Modules.DailyBook.Models import MoneyTransferSummary
    db.session.add(MoneyTransferSummary(
        store_id=store_id, report_date=day, company=company, **kw,
    ))
    db.session.flush()


def _add_transfer(store_id, day, **kw):
    from api.Modules.Transfers.Models import Transfer
    base = dict(
        store_id=store_id, send_date=day, company="Intermex",
        service_type="Money Transfer", sender_name="Test", status="Sent",
        send_amount=0.0, fee=0.0, federal_tax=0.0, commission=0.0,
    )
    base.update(kw)
    db.session.add(Transfer(**base))
    db.session.flush()


def test_commit_aggregates_active_giros_into_intermex_row(test_store_id):
    from api.Modules.ReportImport.Services import (
        commit_intermex_to_mt_breakdown,
    )
    from api.Modules.DailyBook.Services import read_mt_breakdown
    day = date(2026, 5, 1)
    report = _report([
        _giro("1", 100.0, 5.0, 1.0),
        _giro("2", 200.0, 8.0, 2.0),
        _giro("3", 999.0, 9.0, 9.0, cancelled=True),  # excluded
    ])
    with db_session():
        result = commit_intermex_to_mt_breakdown(
            db.session, store_id=test_store_id, report_date=day,
            report=report,
        )
        db.session.commit()

        assert result.giros_committed == 2
        assert result.amount == 300.0
        assert result.fees == 13.0
        assert result.federal_tax == 3.0
        assert result.committed_total == 316.0
        assert result.grand_total == 316.0

        breakdown = read_mt_breakdown(db.session, test_store_id, day)
        intermex = next(r for r in breakdown.rows if r.company == "Intermex")
        assert intermex.saved_amount == 300.0
        assert intermex.saved_fees == 13.0
        assert intermex.saved_federal_tax == 3.0


def test_commit_preserves_other_company_overrides(test_store_id):
    from api.Modules.ReportImport.Services import (
        commit_intermex_to_mt_breakdown,
    )
    from api.Modules.DailyBook.Services import read_mt_breakdown
    day = date(2026, 5, 2)
    with db_session():
        # A manual Maxi override must survive the Intermex commit.
        _add_summary(test_store_id, day, "Maxi", amount=500.0, fees=20.0)
        db.session.commit()

        commit_intermex_to_mt_breakdown(
            db.session, store_id=test_store_id, report_date=day,
            report=_report([_giro("1", 100.0, 5.0, 1.0)]),
        )
        db.session.commit()

        breakdown = read_mt_breakdown(db.session, test_store_id, day)
        maxi = next(r for r in breakdown.rows if r.company == "Maxi")
        assert maxi.saved_amount == 500.0
        assert maxi.saved_fees == 20.0
        intermex = next(r for r in breakdown.rows if r.company == "Intermex")
        assert intermex.saved_amount == 100.0


def test_commit_reconciles_against_logged_transfers(test_store_id):
    from api.Modules.ReportImport.Services import (
        commit_intermex_to_mt_breakdown,
    )
    day = date(2026, 5, 3)
    with db_session():
        # Store already logged $300 of Intermex sends for the day.
        _add_transfer(test_store_id, day, send_amount=300.0, fee=13.0,
                      federal_tax=3.0)
        db.session.commit()

        # Report matches → matches_logged True.
        match = commit_intermex_to_mt_breakdown(
            db.session, store_id=test_store_id, report_date=day,
            report=_report([_giro("1", 300.0, 13.0, 3.0)]),
        )
        assert match.logged_amount == 300.0
        assert match.matches_logged is True
        db.session.commit()

    day2 = date(2026, 5, 4)
    with db_session():
        _add_transfer(test_store_id, day2, send_amount=250.0)
        db.session.commit()
        mismatch = commit_intermex_to_mt_breakdown(
            db.session, store_id=test_store_id, report_date=day2,
            report=_report([_giro("1", 300.0, 13.0, 3.0)]),
        )
        assert mismatch.logged_amount == 250.0
        assert mismatch.matches_logged is False


def test_commit_rejects_no_active_giros(test_store_id):
    from api.Modules.ReportImport.Services import (
        commit_intermex_to_mt_breakdown, ReportCommitError,
    )
    day = date(2026, 5, 5)
    report = _report([_giro("1", 100.0, 5.0, 1.0, cancelled=True)])
    with db_session():
        with pytest.raises(ReportCommitError):
            commit_intermex_to_mt_breakdown(
                db.session, store_id=test_store_id, report_date=day,
                report=report,
            )


def test_commit_rejects_non_reconciling_report(test_store_id):
    from api.Modules.ReportImport.Services import (
        commit_intermex_to_mt_breakdown, ReportCommitError,
    )
    day = date(2026, 5, 6)
    bad = _report([_giro("1", 100.0, 5.0, 1.0)])
    # Force a non-reconciling row.
    object.__setattr__(bad.giros[0], "reconciles", False)
    with db_session():
        with pytest.raises(ReportCommitError):
            commit_intermex_to_mt_breakdown(
                db.session, store_id=test_store_id, report_date=day,
                report=bad,
            )
