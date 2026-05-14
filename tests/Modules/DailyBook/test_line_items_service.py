"""Unit tests for the DailyBook line-item write Service (PR 32)."""
from datetime import date, time, timedelta

import pytest
from tests._app import db, db_session


def _seed_return_check_linked_item(store_id):
    """Create a ReturnCheck row + a linked DailyLineItem so we can
    test the return_check_id linkage guard."""
    from api.Modules.DailyBook.Models import DailyLineItem
    from api.Modules.ReturnChecks.Models import ReturnCheck
    from tests._app import db
    rc = ReturnCheck(
        store_id=store_id, customer_name="X", check_number="1",
        payer_bank="B", amount=100.0, bounced_on=date.today(),
    )
    db.session.add(rc); db.session.commit()
    li = DailyLineItem(
        store_id=store_id, report_date=date.today(),
        kind="return_payback", at_time=time(9, 0),
        amount=100.0, return_check_id=rc.id,
    )
    db.session.add(li); db.session.commit()
    return li


# ── parse_at_time ───────────────────────────────────────────


def test_parse_at_time_accepts_valid_input():
    from api.Modules.DailyBook.Services import parse_at_time
    assert parse_at_time("09:30") == time(9, 30)
    assert parse_at_time("00:00") == time(0, 0)
    assert parse_at_time("23:59") == time(23, 59)


def test_parse_at_time_rejects_malformed():
    from api.Modules.DailyBook.Services import (
        LineItemValidationError, parse_at_time,
    )
    for bad in ("", "abc", "9:30:45", "25:00", "12:60"):
        with pytest.raises(LineItemValidationError) as exc:
            parse_at_time(bad)
        assert "HH:MM" in str(exc.value)


# ── parse_amount ────────────────────────────────────────────


def test_parse_amount_accepts_positive():
    from api.Modules.DailyBook.Services import parse_amount
    assert parse_amount("10") == 10.0
    assert parse_amount("0.01") == 0.01
    assert parse_amount("100.50") == 100.5


def test_parse_amount_rejects_zero_negative_garbage():
    from api.Modules.DailyBook.Services import (
        LineItemValidationError, parse_amount,
    )
    for bad in ("", "0", "-1", "abc", None):
        with pytest.raises(LineItemValidationError) as exc:
            parse_amount(bad)
        assert "greater than zero" in str(exc.value)


# ── add_line_item ───────────────────────────────────────────


def test_add_line_item_inserts_row(test_store_id):
    from api.Modules.DailyBook.Models import DailyLineItem
    from tests._app import db
    from api.Modules.DailyBook.Services import add_line_item
    today = date.today()
    with db_session():
        row = add_line_item(
            db.session,
            store_id=test_store_id, report_date=today,
            kind="cash_expense", at_time=time(10, 0),
            amount=42.50, note="Office supplies",
        )
        db.session.commit()
        assert row.id is not None
        loaded = db.session.get(DailyLineItem, row.id)
    assert loaded.kind == "cash_expense"
    assert loaded.amount == 42.50
    assert loaded.note == "Office supplies"


def test_add_line_item_truncates_long_note(test_store_id):
    from tests._app import db
    from api.Modules.DailyBook.Services import add_line_item
    today = date.today()
    with db_session():
        row = add_line_item(
            db.session,
            store_id=test_store_id, report_date=today,
            kind="cash_expense", at_time=time(10, 0),
            amount=10.0, note="X" * 500,
        )
        db.session.commit()
        assert len(row.note) == 120


def test_add_line_item_with_allowed_kinds_filter_rejects_unknown(test_store_id):
    from tests._app import db
    from api.Modules.DailyBook.Services import (
        LineItemValidationError, add_line_item,
    )
    with db_session():
        with pytest.raises(LineItemValidationError):
            add_line_item(
                db.session,
                store_id=test_store_id, report_date=date.today(),
                kind="garbage", at_time=time(9, 0), amount=1.0,
                allowed_kinds={"cash_expense", "cash_purchase"},
            )


# ── delete_line_item ────────────────────────────────────────


def test_delete_line_item_removes_row(test_store_id):
    from api.Modules.DailyBook.Models import DailyLineItem
    from tests._app import db
    from api.Modules.DailyBook.Services import (
        add_line_item, delete_line_item,
    )
    today = date.today()
    with db_session():
        row = add_line_item(
            db.session,
            store_id=test_store_id, report_date=today,
            kind="cash_expense", at_time=time(10, 0), amount=1.0,
        )
        db.session.commit()
        rid = row.id
        delete_line_item(db.session, row)
        db.session.commit()
        assert db.session.get(DailyLineItem, rid) is None


def test_delete_line_item_blocks_return_check_linked(test_store_id):
    """A line item created from a Return-Check payment can't be
    deleted via the daily-book delete path — the daily book stays in
    sync with the Return Checks page."""
    from tests._app import db
    from api.Modules.DailyBook.Services import (
        LineItemValidationError, delete_line_item,
    )
    with db_session():
        li = _seed_return_check_linked_item(test_store_id)
        with pytest.raises(LineItemValidationError) as exc:
            delete_line_item(db.session, li)
    assert "return check" in str(exc.value).lower()


def test_delete_line_item_allows_return_check_when_flag_set(test_store_id):
    """The Return-Checks-side delete path passes
    `allow_return_check_linked=True` to bypass the gate."""
    from api.Modules.DailyBook.Models import DailyLineItem
    from tests._app import db
    from api.Modules.DailyBook.Services import delete_line_item
    with db_session():
        li = _seed_return_check_linked_item(test_store_id)
        rid = li.id
        delete_line_item(
            db.session, li, allow_return_check_linked=True,
        )
        db.session.commit()
        assert db.session.get(DailyLineItem, rid) is None


# ── recompute_line_items_total ──────────────────────────────


def test_recompute_sums_kind_and_writes_back(test_store_id):
    """Σ DailyLineItem.amount where kind matches → DailyReport
    field. Other kinds + other dates ignored."""
    from api.Modules.DailyBook.Models import DailyReport
    from tests._app import db
    from api.Modules.DailyBook.Services import (
        add_line_item, recompute_line_items_total,
    )
    today = date.today()
    with db_session():
        # Three cash_expense lines today (10 + 20 + 5 = 35.0)
        for amt in (10.0, 20.0, 5.0):
            add_line_item(
                db.session,
                store_id=test_store_id, report_date=today,
                kind="cash_expense", at_time=time(9, 0), amount=amt,
            )
        # Different kind today (must NOT count toward cash_expense)
        add_line_item(
            db.session,
            store_id=test_store_id, report_date=today,
            kind="cash_purchase", at_time=time(9, 0), amount=999.0,
        )
        # cash_expense yesterday (must NOT count for today)
        add_line_item(
            db.session,
            store_id=test_store_id,
            report_date=today - timedelta(days=1),
            kind="cash_expense", at_time=time(9, 0), amount=777.0,
        )
        db.session.commit()
        total = recompute_line_items_total(
            db.session, test_store_id, today,
            kind="cash_expense",
            daily_report_field="cash_expense",
        )
        db.session.commit()
        assert total == 35.0
        # The rolled-up total landed on the report row
        rpt = (
            db.session.query(DailyReport)
              .filter_by(store_id=test_store_id, report_date=today)
              .first()
        )
        assert rpt is not None
        assert rpt.cash_expense == 35.0


def test_recompute_zeroes_field_when_no_line_items(test_store_id):
    """If all line items of a kind are deleted, the recompute pushes
    0.0 onto the field — clearing stale totals."""
    from api.Modules.DailyBook.Models import DailyReport
    from tests._app import db
    from api.Modules.DailyBook.Services import recompute_line_items_total
    today = date.today()
    with db_session():
        # Seed a DailyReport with a non-zero cash_expense (simulating
        # an old recompute) but no line items
        rpt = DailyReport(
            store_id=test_store_id, report_date=today,
            cash_expense=50.0,
        )
        db.session.add(rpt); db.session.commit()
        # Recompute — should drop to 0
        total = recompute_line_items_total(
            db.session, test_store_id, today,
            kind="cash_expense", daily_report_field="cash_expense",
        )
        db.session.commit()
        assert total == 0.0
        rpt = db.session.get(DailyReport, rpt.id)
        assert rpt.cash_expense == 0.0


def test_recompute_creates_report_if_missing(test_store_id):
    """Recompute calls ensure_daily_report — empty days get a row."""
    from api.Modules.DailyBook.Models import DailyReport
    from tests._app import db
    from api.Modules.DailyBook.Services import recompute_line_items_total
    today = date.today()
    with db_session():
        recompute_line_items_total(
            db.session, test_store_id, today,
            kind="cash_expense", daily_report_field="cash_expense",
        )
        db.session.commit()
        rpt = (
            db.session.query(DailyReport)
              .filter_by(store_id=test_store_id, report_date=today)
              .first()
        )
        assert rpt is not None
