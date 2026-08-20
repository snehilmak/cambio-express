"""Payroll cash/check split — backfill migration + monthly P&L feed.

The daily book's typed ``payroll_expense`` becomes two line-item
kinds: ``payroll_cash`` (still a daily disbursement) and
``payroll_check`` (invisible to daily totals, feeds the monthly
``check_payroll`` P&L line). Backfill mirrors the from_bank /
money_order conversions.
"""
from __future__ import annotations

import importlib.util
from datetime import date
from pathlib import Path

from tests._app import db, db_session


def _load_migration():
    path = (
        Path(__file__).resolve().parents[3]
        / "alembic" / "versions"
        / "b3e7c1f9d5a2_payroll_check_split.py"
    )
    spec = importlib.util.spec_from_file_location("_payroll_split_mig", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _payroll_cash_items(store_id: int, day: date):
    from api.Modules.DailyBook.Models import DailyLineItem
    return (
        db.session.query(DailyLineItem)
        .filter_by(store_id=store_id, report_date=day, kind="payroll_cash")
        .all()
    )


def test_backfill_seeds_positive_reports_only_and_is_idempotent(test_store_id):
    from api.Modules.DailyBook.Models import DailyLineItem, DailyReport
    mig = _load_migration()
    d_pos = date(2026, 3, 10)
    d_zero = date(2026, 3, 11)
    d_existing = date(2026, 3, 12)

    with db_session():
        db.session.add(DailyReport(
            store_id=test_store_id, report_date=d_pos, payroll_expense=800.0,
        ))
        db.session.add(DailyReport(
            store_id=test_store_id, report_date=d_zero, payroll_expense=0.0,
        ))
        db.session.add(DailyReport(
            store_id=test_store_id, report_date=d_existing,
            payroll_expense=250.0,
        ))
        db.session.add(DailyLineItem(
            store_id=test_store_id, report_date=d_existing,
            kind="payroll_cash", amount=250.0,
        ))
        db.session.flush()

        seeded = mig.backfill_payroll_cash_line_items(db.session.connection())
        assert seeded == 1

        pos_items = _payroll_cash_items(test_store_id, d_pos)
        assert len(pos_items) == 1
        assert pos_items[0].amount == 800.0

        assert _payroll_cash_items(test_store_id, d_zero) == []
        assert len(_payroll_cash_items(test_store_id, d_existing)) == 1

        again = mig.backfill_payroll_cash_line_items(db.session.connection())
        assert again == 0


def test_monthly_check_payroll_derives_from_daily(test_store_id):
    """MonthlyFinancial.check_payroll sums DailyReport.payroll_check
    over the month and lands in total_expenses — the whole point of
    the check-payroll kind (checks skip the daily book but must hit
    the P&L)."""
    from api.Modules.DailyBook.Models import DailyReport
    from api.Modules.Monthly.Services.write import _DAILY_DERIVED_FIELDS, _sum_daily

    assert _DAILY_DERIVED_FIELDS["check_payroll"] == "payroll_check"
    with db_session():
        db.session.add(DailyReport(
            store_id=test_store_id, report_date=date(2026, 4, 3),
            payroll_check=1200.0,
        ))
        db.session.add(DailyReport(
            store_id=test_store_id, report_date=date(2026, 4, 17),
            payroll_check=800.0,
        ))
        # A different month must not leak in.
        db.session.add(DailyReport(
            store_id=test_store_id, report_date=date(2026, 5, 1),
            payroll_check=999.0,
        ))
        db.session.commit()
        assert _sum_daily(
            db.session, test_store_id, 2026, 4,
            daily_field="payroll_check",
        ) == 2000.0


def test_check_payroll_in_monthly_total_expenses(test_store_id):
    from api.Modules.Monthly.Models import MonthlyFinancial
    with db_session():
        row = MonthlyFinancial(
            store_id=test_store_id, year=2026, month=4,
            cash_payroll=500.0, check_payroll=2000.0,
        )
        db.session.add(row)
        db.session.flush()
        assert row.total_expenses == 2500.0
