"""Unit tests for DailyBook.Repositories — reports, line_items."""
from datetime import date, time, timedelta


def _seed_report(store_id, report_date, *, taxable_sales=0.0, **kwargs):
    from api.Modules.DailyBook.Models import DailyReport
    from tests._app import db
    r = DailyReport(
        store_id=store_id, report_date=report_date,
        taxable_sales=taxable_sales, **kwargs,
    )
    db.session.add(r); db.session.commit()
    return r.id


def _seed_line_item(store_id, report_date, *, kind="cash_expense",
                     amount=10.0, at_time=None, note=""):
    from api.Modules.DailyBook.Models import DailyLineItem
    from tests._app import db
    li = DailyLineItem(
        store_id=store_id, report_date=report_date, kind=kind,
        at_time=at_time or time(9, 0), amount=amount, note=note,
    )
    db.session.add(li); db.session.commit()
    return li.id


# ── reports ─────────────────────────────────────────────────


def test_find_report_by_date_returns_match(test_store_id):
    from tests._app import app as flask_app, db
    from api.Modules.DailyBook.Repositories import find_report_by_date
    today = date.today()
    with flask_app.app_context():
        rid = _seed_report(test_store_id, today, taxable_sales=100.0)
        r = find_report_by_date(db.session, test_store_id, today)
    assert r is not None
    assert r.id == rid
    assert r.taxable_sales == 100.0


def test_find_report_by_date_returns_none_when_missing(test_store_id):
    from tests._app import app as flask_app, db
    from api.Modules.DailyBook.Repositories import find_report_by_date
    with flask_app.app_context():
        r = find_report_by_date(
            db.session, test_store_id, date.today(),
        )
    assert r is None


def test_find_report_by_date_isolates_other_stores(test_store_id):
    from api.Modules.Tenancy.Models import Store
    from tests._app import app as flask_app, db
    from api.Modules.DailyBook.Repositories import find_report_by_date
    today = date.today()
    with flask_app.app_context():
        s2 = Store(name="Other", slug="other-db",
                    email="o@x.com", plan="trial")
        db.session.add(s2); db.session.commit()
        sid2 = s2.id
        _seed_report(sid2, today, taxable_sales=999.0)
        r = find_report_by_date(db.session, test_store_id, today)
    assert r is None


# ── get_report_by_id ────────────────────────────────────────


def test_get_report_by_id_returns_in_scope(test_store_id):
    from tests._app import app as flask_app, db
    from api.Modules.DailyBook.Repositories import get_report_by_id
    with flask_app.app_context():
        rid = _seed_report(test_store_id, date.today())
        r = get_report_by_id(db.session, rid, [test_store_id])
    assert r is not None
    assert r.id == rid


def test_get_report_by_id_none_outside_scope(test_store_id):
    from api.Modules.Tenancy.Models import Store
    from tests._app import app as flask_app, db
    from api.Modules.DailyBook.Repositories import get_report_by_id
    with flask_app.app_context():
        s2 = Store(name="Other", slug="other-db-2",
                    email="o@x.com", plan="trial")
        db.session.add(s2); db.session.commit()
        rid = _seed_report(s2.id, date.today())
        r = get_report_by_id(db.session, rid, [test_store_id])
    assert r is None


# ── list_reports_in_period ──────────────────────────────────


def test_list_reports_in_period_orders_by_date(test_store_id):
    from tests._app import app as flask_app, db
    from api.Modules.DailyBook.Repositories import list_reports_in_period
    today = date.today()
    yesterday = today - timedelta(days=1)
    last_week = today - timedelta(days=7)
    with flask_app.app_context():
        _seed_report(test_store_id, last_week, taxable_sales=1.0)
        _seed_report(test_store_id, today, taxable_sales=3.0)
        _seed_report(test_store_id, yesterday, taxable_sales=2.0)
        rows = list_reports_in_period(
            db.session, [test_store_id], last_week, today,
        )
    assert [r.taxable_sales for r in rows] == [1.0, 2.0, 3.0]


def test_list_reports_in_period_excludes_out_of_range(test_store_id):
    from tests._app import app as flask_app, db
    from api.Modules.DailyBook.Repositories import list_reports_in_period
    today = date.today()
    last_year = today - timedelta(days=365)
    with flask_app.app_context():
        _seed_report(test_store_id, last_year, taxable_sales=999.0)
        _seed_report(test_store_id, today, taxable_sales=100.0)
        rows = list_reports_in_period(
            db.session, [test_store_id], today, today,
        )
    assert len(rows) == 1
    assert rows[0].taxable_sales == 100.0


def test_list_reports_in_period_isolates_other_stores(test_store_id):
    from api.Modules.Tenancy.Models import Store
    from tests._app import app as flask_app, db
    from api.Modules.DailyBook.Repositories import list_reports_in_period
    today = date.today()
    with flask_app.app_context():
        s2 = Store(name="Other", slug="other-db-3",
                    email="o@x.com", plan="trial")
        db.session.add(s2); db.session.commit()
        _seed_report(s2.id, today, taxable_sales=777.0)
        _seed_report(test_store_id, today, taxable_sales=100.0)
        rows = list_reports_in_period(
            db.session, [test_store_id], today, today,
        )
    assert {r.taxable_sales for r in rows} == {100.0}


# ── line_items ──────────────────────────────────────────────


def test_list_line_items_orders_by_time(test_store_id):
    from tests._app import app as flask_app, db
    from api.Modules.DailyBook.Repositories import list_line_items
    today = date.today()
    with flask_app.app_context():
        _seed_line_item(
            test_store_id, today, at_time=time(15, 0),
            note="LATE", amount=1.0,
        )
        _seed_line_item(
            test_store_id, today, at_time=time(9, 0),
            note="EARLY", amount=2.0,
        )
        items = list_line_items(db.session, test_store_id, today)
    assert [li.note for li in items] == ["EARLY", "LATE"]


def test_list_line_items_kinds_filter(test_store_id):
    from tests._app import app as flask_app, db
    from api.Modules.DailyBook.Repositories import list_line_items
    today = date.today()
    with flask_app.app_context():
        _seed_line_item(test_store_id, today, kind="cash_expense", note="A")
        _seed_line_item(test_store_id, today, kind="check_expense", note="B")
        items = list_line_items(
            db.session, test_store_id, today, kinds=["cash_expense"],
        )
    assert {li.note for li in items} == {"A"}


def test_list_line_items_empty_kinds_returns_empty(test_store_id):
    """Passing `kinds=[]` short-circuits before the DB query."""
    from tests._app import app as flask_app, db
    from api.Modules.DailyBook.Repositories import list_line_items
    today = date.today()
    with flask_app.app_context():
        _seed_line_item(test_store_id, today)
        items = list_line_items(
            db.session, test_store_id, today, kinds=[],
        )
    assert items == []


def test_list_line_items_scoped_to_date_and_store(test_store_id):
    """Items from other dates or stores must NOT appear."""
    from api.Modules.Tenancy.Models import Store
    from tests._app import app as flask_app, db
    from api.Modules.DailyBook.Repositories import list_line_items
    today = date.today()
    yesterday = today - timedelta(days=1)
    with flask_app.app_context():
        s2 = Store(name="Other", slug="other-db-4",
                    email="o@x.com", plan="trial")
        db.session.add(s2); db.session.commit()
        _seed_line_item(s2.id, today, note="OTHER_STORE")
        _seed_line_item(test_store_id, yesterday, note="OTHER_DATE")
        _seed_line_item(test_store_id, today, note="MINE")
        items = list_line_items(db.session, test_store_id, today)
    assert {li.note for li in items} == {"MINE"}


def test_sum_line_items_by_kind(test_store_id):
    from tests._app import app as flask_app, db
    from api.Modules.DailyBook.Repositories import sum_line_items_by_kind
    today = date.today()
    with flask_app.app_context():
        _seed_line_item(test_store_id, today, kind="cash_expense",
                          amount=10.0)
        _seed_line_item(test_store_id, today, kind="cash_expense",
                          amount=20.0)
        # Different kind — must be excluded
        _seed_line_item(test_store_id, today, kind="check_expense",
                          amount=999.0)
        total = sum_line_items_by_kind(
            db.session, test_store_id, today, "cash_expense",
        )
    assert total == 30.0


def test_sum_line_items_by_kind_zero_when_empty(test_store_id):
    from tests._app import app as flask_app, db
    from api.Modules.DailyBook.Repositories import sum_line_items_by_kind
    with flask_app.app_context():
        total = sum_line_items_by_kind(
            db.session, test_store_id, date.today(), "cash_expense",
        )
    assert total == 0.0
