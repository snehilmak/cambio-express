"""Unit tests for DailyBook.Services (read-side)."""
from datetime import date, datetime, timedelta
from tests._app import db, db_session


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
    from tests._app import db
    from api.Modules.DailyBook.Services import summarize_report
    with db_session():
        s = summarize_report(db.session, test_store_id, date.today())
    assert s is None


def test_summarize_report_computes_totals(test_store_id):
    from tests._app import db
    from api.Modules.DailyBook.Services import summarize_report
    today = date.today()
    with db_session():
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
    from tests._app import db
    from api.Modules.DailyBook.Services import summarize_report
    today = date.today()
    with db_session():
        _seed_report(
            test_store_id, today, taxable_sales=10.0,
            locked_at=datetime.utcnow(),
        )
        s = summarize_report(db.session, test_store_id, today)
    assert s.locked is True


def test_summarize_report_unlocked_default(test_store_id):
    from tests._app import db
    from api.Modules.DailyBook.Services import summarize_report
    today = date.today()
    with db_session():
        _seed_report(test_store_id, today, taxable_sales=10.0)
        s = summarize_report(db.session, test_store_id, today)
    assert s.locked is False


# ── summarize_period ────────────────────────────────────────


def test_summarize_period_empty_safe(test_store_id):
    from tests._app import db
    from api.Modules.DailyBook.Services import summarize_period
    today = date.today()
    with db_session():
        s = summarize_period(
            db.session, [test_store_id], today, today,
        )
    assert s.rows == []
    assert s.total_receipts == 0
    assert s.total_disbursements == 0
    assert s.net == 0
    assert s.days_logged == 0


def test_summarize_period_aggregates(test_store_id):
    from tests._app import db
    from api.Modules.DailyBook.Services import summarize_period
    today = date.today()
    yesterday = today - timedelta(days=1)
    with db_session():
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
    from tests._app import db
    from api.Modules.DailyBook.Services import summarize_period
    today = date.today()
    with db_session():
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
    from tests._app import db
    from api.Modules.DailyBook.Services import summarize_period
    from api.Modules.DailyBook.Requests import (
        DailyReportRow, PeriodSummaryResponse,
    )
    today = date.today()
    with db_session():
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


# ── Forward-balance carry-forward ───────────────────────────
#
# forward_balance auto-carries from the previous logged day
# (outside_cash_drops + safe_balance). The first logged day has no
# prior report, so the operator seeds it by hand and it stays
# editable; every day after is auto + read-only.


def test_forward_balance_first_day_is_manual(test_store_id):
    from tests._app import db
    from api.Modules.DailyBook.Services import summarize_report
    d = date(2026, 3, 2)
    with db_session():
        _seed_report(test_store_id, d, forward_balance=500.0)
        s = summarize_report(db.session, test_store_id, d)
    assert s is not None
    # No earlier report → operator-seeded value stands, editable.
    assert s.forward_balance_auto is False
    assert s.forward_balance == 500.0


def test_forward_balance_carries_on_fresh_unsaved_day(test_store_id):
    """The bug the operator hit: they filled yesterday (safe + drops)
    but today's report row doesn't exist yet. summarize_report must
    still return the carried forward balance (read-only) instead of
    None — otherwise the editor shows a blank, editable box."""
    from tests._app import db
    from api.Modules.DailyBook.Services import summarize_report
    day1 = date(2026, 4, 1)
    day2 = date(2026, 4, 2)  # never saved — no DailyReport row
    with db_session():
        _seed_report(
            test_store_id, day1,
            outside_cash_drops=90.0, safe_balance=410.0,
        )
        s = summarize_report(db.session, test_store_id, day2)
    assert s is not None, "fresh day with a prior must not 404"
    assert s.id == 0                       # virtual, not persisted
    assert s.forward_balance == 500.0      # 90 drops + 410 safe
    assert s.forward_balance_auto is True  # read-only in the editor
    assert s.total_receipts == 500.0
    assert s.net == 500.0


def test_forward_balance_carries_from_prior_day(test_store_id):
    from tests._app import db
    from api.Modules.DailyBook.Services import summarize_report
    day1 = date(2026, 3, 2)
    day2 = date(2026, 3, 3)
    with db_session():
        # Prior day left 120 dropped to the safe + 380 in the safe.
        _seed_report(
            test_store_id, day1,
            outside_cash_drops=120.0, safe_balance=380.0,
            forward_balance=500.0,
        )
        # Day 2's own stored forward is deliberately stale (0); the
        # summary must override it with the carried value.
        _seed_report(test_store_id, day2, taxable_sales=100.0,
                     forward_balance=0.0)
        s = summarize_report(db.session, test_store_id, day2)
    assert s is not None
    assert s.forward_balance_auto is True
    assert s.forward_balance == 500.0  # 120 drops + 380 safe
    # The carried value flows into receipts even though the stored
    # column was stale.
    assert s.total_receipts == 600.0   # 100 taxable + 500 forward
    assert s.net == s.total_receipts - s.total_disbursements


def test_forward_balance_skips_gap_days(test_store_id):
    """Carry comes from the most recent *logged* prior day, not a
    fixed 'yesterday' — a store closed a day still carries."""
    from tests._app import db
    from api.Modules.DailyBook.Services import summarize_report
    sat = date(2026, 3, 7)
    mon = date(2026, 3, 9)  # Sunday (the 8th) skipped
    with db_session():
        _seed_report(test_store_id, sat,
                     outside_cash_drops=50.0, safe_balance=250.0)
        _seed_report(test_store_id, mon)
        s = summarize_report(db.session, test_store_id, mon)
    assert s.forward_balance_auto is True
    assert s.forward_balance == 300.0  # Saturday's 50 + 250


def test_update_forces_forward_balance_on_carried_day(test_store_id):
    """A stale / tampered client forward_balance can't overwrite the
    carried value on a day that has a prior report."""
    from tests._app import db
    from api.Modules.DailyBook.Services import (
        summarize_report, update_daily_report,
    )
    day1 = date(2026, 3, 2)
    day2 = date(2026, 3, 3)
    with db_session():
        _seed_report(test_store_id, day1,
                     outside_cash_drops=100.0, safe_balance=400.0)
        update_daily_report(
            db.session, store_id=test_store_id, report_date=day2,
            fields={"forward_balance": 9999.0, "taxable_sales": 10.0},
        )
        db.session.commit()
        s = summarize_report(db.session, test_store_id, day2)
    # Client sent 9999 but the server forced the carry (100 + 400).
    assert s.forward_balance == 500.0
    assert s.forward_balance_auto is True


def test_update_honors_seed_on_first_day(test_store_id):
    """The very first logged day has no prior report — the operator's
    seeded forward_balance is honoured and stays editable."""
    from tests._app import db
    from api.Modules.DailyBook.Services import (
        summarize_report, update_daily_report,
    )
    d = date(2026, 3, 2)
    with db_session():
        update_daily_report(
            db.session, store_id=test_store_id, report_date=d,
            fields={"forward_balance": 750.0},
        )
        db.session.commit()
        s = summarize_report(db.session, test_store_id, d)
    assert s.forward_balance == 750.0
    assert s.forward_balance_auto is False
