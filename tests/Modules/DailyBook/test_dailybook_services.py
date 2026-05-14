"""Unit tests for DailyBook.Services (read-side)."""
from datetime import date, datetime, timedelta


def _seed_report(store_id, report_date, **kwargs):
    from api.Modules.DailyBook.Models import DailyReport
    from tests._app import db
    r = DailyReport(
        store_id=store_id, report_date=report_date, **kwargs,
    )
    db.session.add(r); db.session.commit()
    return r.id


# ── summarize_report ────────────────────────────────────────


def test_summarize_report_returns_none_when_missing(test_store_id):
    from tests._app import app as flask_app, db
    from api.Modules.DailyBook.Services import summarize_report
    with flask_app.app_context():
        s = summarize_report(db.session, test_store_id, date.today())
    assert s is None


def test_summarize_report_computes_totals(test_store_id):
    from tests._app import app as flask_app, db
    from api.Modules.DailyBook.Services import summarize_report
    today = date.today()
    with flask_app.app_context():
        _seed_report(
            test_store_id, today,
            taxable_sales=100.0, non_taxable=50.0, sales_tax=10.0,
            cash_expense=20.0, check_expense=5.0,
        )
        s = summarize_report(db.session, test_store_id, today)
    assert s is not None
    assert s.taxable_sales == 100.0
    # total_receipts spans every "in" field — taxable+non_taxable+
    # sales_tax + (other zero-defaulted fields)
    assert s.total_receipts >= 160.0  # at least these three
    assert s.total_disbursements >= 25.0  # cash + check expense
    assert s.net == s.total_receipts - s.total_disbursements


def test_summarize_report_locked_state(test_store_id):
    from tests._app import app as flask_app, db
    from api.Modules.DailyBook.Services import summarize_report
    today = date.today()
    with flask_app.app_context():
        _seed_report(
            test_store_id, today, taxable_sales=10.0,
            locked_at=datetime.utcnow(),
        )
        s = summarize_report(db.session, test_store_id, today)
    assert s.locked is True


def test_summarize_report_unlocked_default(test_store_id):
    from tests._app import app as flask_app, db
    from api.Modules.DailyBook.Services import summarize_report
    today = date.today()
    with flask_app.app_context():
        _seed_report(test_store_id, today, taxable_sales=10.0)
        s = summarize_report(db.session, test_store_id, today)
    assert s.locked is False


# ── summarize_period ────────────────────────────────────────


def test_summarize_period_empty_safe(test_store_id):
    from tests._app import app as flask_app, db
    from api.Modules.DailyBook.Services import summarize_period
    today = date.today()
    with flask_app.app_context():
        s = summarize_period(
            db.session, [test_store_id], today, today,
        )
    assert s.rows == []
    assert s.total_receipts == 0
    assert s.total_disbursements == 0
    assert s.net == 0
    assert s.days_logged == 0


def test_summarize_period_aggregates(test_store_id):
    from tests._app import app as flask_app, db
    from api.Modules.DailyBook.Services import summarize_period
    today = date.today()
    yesterday = today - timedelta(days=1)
    with flask_app.app_context():
        _seed_report(test_store_id, yesterday, taxable_sales=100.0)
        _seed_report(test_store_id, today, taxable_sales=200.0,
                     cash_expense=50.0)
        s = summarize_period(
            db.session, [test_store_id], yesterday, today,
        )
    assert s.days_logged == 2
    assert s.total_receipts == 300.0
    assert s.total_disbursements == 50.0
    assert s.net == 250.0
    # date-asc ordering
    assert [r.report_date for r in s.rows] == [
        yesterday.isoformat(), today.isoformat(),
    ]


def test_summarize_period_isolates_other_stores(test_store_id):
    from api.Modules.Tenancy.Models import Store
    from tests._app import app as flask_app, db
    from api.Modules.DailyBook.Services import summarize_period
    today = date.today()
    with flask_app.app_context():
        s2 = Store(name="Other", slug="other-db-svc",
                    email="o@x.com", plan="trial")
        db.session.add(s2); db.session.commit()
        _seed_report(s2.id, today, taxable_sales=999.0)
        _seed_report(test_store_id, today, taxable_sales=100.0)
        s = summarize_period(
            db.session, [test_store_id], today, today,
        )
    assert s.total_receipts == 100.0


# ── Pydantic schema validation ──────────────────────────────


def test_period_summary_response_validates(test_store_id):
    from tests._app import app as flask_app, db
    from api.Modules.DailyBook.Services import summarize_period
    from api.Modules.DailyBook.Requests import (
        DailyReportRow, PeriodSummaryResponse,
    )
    today = date.today()
    with flask_app.app_context():
        _seed_report(test_store_id, today, taxable_sales=100.0)
        s = summarize_period(
            db.session, [test_store_id], today, today,
        )
        rows = [
            DailyReportRow(
                id=r.id, store_id=r.store_id,
                report_date=r.report_date,
                taxable_sales=r.taxable_sales,
                non_taxable=r.non_taxable,
                sales_tax=r.sales_tax,
                money_transfer=r.money_transfer,
                money_order=r.money_order,
                cash_expense=r.cash_expense,
                check_expense=r.check_expense,
                cash_deposit=r.cash_deposit,
                checks_deposit=r.checks_deposit,
                safe_balance=r.safe_balance,
                over_short=r.over_short,
                locked=r.locked,
                notes=r.notes,
                total_receipts=r.total_receipts,
                total_disbursements=r.total_disbursements,
                net=r.net,
            )
            for r in s.rows
        ]
        resp = PeriodSummaryResponse(
            rows=rows,
            total_receipts=s.total_receipts,
            total_disbursements=s.total_disbursements,
            net=s.net,
            days_logged=s.days_logged,
        )
    assert resp.days_logged == 1
    assert resp.rows[0].taxable_sales == 100.0
