"""Generic DailyLineItem widget — one row per add, totals derived
onto DailyReport fields via _LINE_ITEM_KINDS. Regression guards
parametrized across every kind so new kinds inherit coverage for
free (just add the kind to _LINE_ITEM_KINDS).
"""
import json
from datetime import date, time

import pytest


# Kinds + corresponding DailyReport field + template label. Keep this
# in lockstep with app.py::_LINE_ITEM_KINDS.
KINDS = [
    ("return_payback", "return_check_paid_back", "Return Check Paid Back"),
    ("cash_purchase",  "cash_purchases",         "Cash Purchases"),
    ("cash_expense",   "cash_expense",           "Cash Expense"),
    ("check_purchase", "check_purchases",        "Check Purchases"),
    ("check_expense",  "check_expense",          "Check Expense"),
    ("other_cash_in",  "other_cash_in",          "Other Cash In"),
    ("other_cash_out", "other_cash_out",         "Other Cash Out"),
]

# Kinds whose widget is editable in the daily book. `return_payback`
# moved to a read-only auto-populated mode (source of truth is
# Books → Return Checks). The widget render + AJAX-add tests only
# apply to editable kinds; the still-derived-from-line-items
# semantics (test_field_is_derived_on_daily_save) apply to all kinds
# including the read-only one.
EDITABLE_KINDS = [(k, f, l) for (k, f, l) in KINDS if k != "return_payback"]


def _today_ds():
    return date.today().isoformat()


@pytest.mark.parametrize("kind,field,label", EDITABLE_KINDS)
def test_widget_renders_on_daily_report(logged_in_client, test_store_id,
                                        kind, field, label):
    from app import DailyLineItem, db
    ds = _today_ds()
    with logged_in_client.application.app_context():
        db.session.add(DailyLineItem(
            store_id=test_store_id, report_date=date.today(), kind=kind,
            at_time=time(9, 0), amount=125.0, note=f"seed {kind}",
        ))
        db.session.commit()

    resp = logged_in_client.get(f"/daily/{ds}")
    assert resp.status_code == 200
    body = resp.data.decode()
    assert f'id="li-{kind}-details"' in body
    assert f'id="li-{kind}-tbody"' in body
    assert f"/daily/{ds}/line-items/{kind}/new" in body
    assert label in body
    assert f"seed {kind}" in body
    assert "$125.00" in body
    # Readonly derived input carries the right name + value
    assert f'name="{field}"' in body


@pytest.mark.parametrize("kind,field,_", KINDS)
def test_field_is_derived_on_daily_save(logged_in_client, test_store_id,
                                        kind, field, _):
    """Posting the daily-report form with a spoofed value must NOT
    overwrite the derived total from DailyLineItem rows."""
    from app import DailyLineItem, DailyReport, db
    ds = _today_ds()
    with logged_in_client.application.app_context():
        db.session.add(DailyLineItem(
            store_id=test_store_id, report_date=date.today(), kind=kind,
            at_time=time(9, 0), amount=200.0,
        ))
        db.session.add(DailyLineItem(
            store_id=test_store_id, report_date=date.today(), kind=kind,
            at_time=time(16, 0), amount=300.0,
        ))
        db.session.commit()

    resp = logged_in_client.post(f"/daily/{ds}", data={field: "999999"})
    assert resp.status_code in (200, 302)

    with logged_in_client.application.app_context():
        rpt = DailyReport.query.filter_by(
            store_id=test_store_id, report_date=date.today()
        ).first()
        assert rpt is not None
        assert getattr(rpt, field) == 500.0, \
            f"{field} not derived: expected 500.0, got {getattr(rpt, field)}"


@pytest.mark.parametrize("kind,field,_", EDITABLE_KINDS)
def test_ajax_add_delete_round_trip(logged_in_client, test_store_id,
                                    kind, field, _):
    """Add, add, delete — payload shape and DailyReport field update
    correctly for every kind."""
    from app import DailyReport, db
    ds = _today_ds()

    r1 = logged_in_client.post(
        f"/daily/{ds}/line-items/{kind}/new",
        data={"at_time": "09:15", "amount": "250.50", "note": "First"},
        headers={"Accept": "application/json"},
    )
    assert r1.status_code == 200
    p1 = json.loads(r1.data)
    assert p1["ok"] is True
    assert p1["kind"] == kind
    assert p1["total"] == 250.5
    assert len(p1["items"]) == 1
    first_id = p1["items"][0]["id"]

    r2 = logged_in_client.post(
        f"/daily/{ds}/line-items/{kind}/new",
        data={"at_time": "14:45", "amount": "100.00", "note": "Second"},
        headers={"Accept": "application/json"},
    )
    p2 = json.loads(r2.data)
    assert p2["total"] == 350.5
    assert len(p2["items"]) == 2

    # DailyReport field reflects the running total
    with logged_in_client.application.app_context():
        rpt = DailyReport.query.filter_by(
            store_id=test_store_id, report_date=date.today()
        ).first()
        assert getattr(rpt, field) == 350.5

    # Delete the first row
    r3 = logged_in_client.post(
        f"/daily/{ds}/line-items/{kind}/{first_id}/delete",
        headers={"Accept": "application/json"},
    )
    p3 = json.loads(r3.data)
    assert p3["ok"] is True
    assert p3["total"] == 100.0

    with logged_in_client.application.app_context():
        rpt = DailyReport.query.filter_by(
            store_id=test_store_id, report_date=date.today()
        ).first()
        assert getattr(rpt, field) == 100.0


def test_unknown_kind_returns_404(logged_in_client):
    """Malformed kind in URL must not create an orphan row."""
    from app import DailyLineItem
    ds = _today_ds()
    r = logged_in_client.post(
        f"/daily/{ds}/line-items/bogus/new",
        data={"at_time": "09:00", "amount": "50"},
        headers={"Accept": "application/json"},
    )
    assert r.status_code == 404

    with logged_in_client.application.app_context():
        assert DailyLineItem.query.count() == 0


def test_kinds_are_isolated_from_each_other(logged_in_client, test_store_id):
    """Rows of one kind must not leak into another kind's total."""
    from app import DailyLineItem, DailyReport, db
    ds = _today_ds()
    with logged_in_client.application.app_context():
        db.session.add(DailyLineItem(
            store_id=test_store_id, report_date=date.today(),
            kind="cash_purchase", at_time=time(9, 0), amount=100.0,
        ))
        db.session.add(DailyLineItem(
            store_id=test_store_id, report_date=date.today(),
            kind="cash_expense", at_time=time(10, 0), amount=25.0,
        ))
        db.session.commit()

    # Trigger a recompute on save
    logged_in_client.post(f"/daily/{ds}", data={})
    with logged_in_client.application.app_context():
        rpt = DailyReport.query.filter_by(
            store_id=test_store_id, report_date=date.today()
        ).first()
        assert rpt.cash_purchases == 100.0
        assert rpt.cash_expense == 25.0
        # Other 3 fields untouched (0.0) because no rows of those kinds
        assert rpt.check_purchases == 0.0
        assert rpt.check_expense == 0.0
        assert rpt.return_check_paid_back == 0.0


def test_ajax_rejects_invalid_time_and_amount(logged_in_client):
    from app import DailyLineItem
    ds = _today_ds()

    r = logged_in_client.post(
        f"/daily/{ds}/line-items/cash_purchase/new",
        data={"at_time": "not-a-time", "amount": "50"},
        headers={"Accept": "application/json"},
    )
    assert r.status_code == 400
    assert json.loads(r.data)["ok"] is False

    r = logged_in_client.post(
        f"/daily/{ds}/line-items/cash_purchase/new",
        data={"at_time": "09:00", "amount": "0"},
        headers={"Accept": "application/json"},
    )
    assert r.status_code == 400

    with logged_in_client.application.app_context():
        assert DailyLineItem.query.count() == 0


def test_line_items_isolated_per_store(logged_in_client, test_store_id):
    """A DailyLineItem owned by another store must not leak into this
    store's report or AJAX payload."""
    from app import Store, DailyLineItem, db
    ds = _today_ds()
    with logged_in_client.application.app_context():
        other = Store(name="Other Store", slug="other-store-li", plan="trial")
        db.session.add(other); db.session.flush()
        db.session.add(DailyLineItem(
            store_id=other.id, report_date=date.today(),
            kind="cash_purchase", at_time=time(12, 0),
            amount=9999.0, note="NOT MINE",
        ))
        db.session.add(DailyLineItem(
            store_id=test_store_id, report_date=date.today(),
            kind="cash_purchase", at_time=time(9, 0),
            amount=50.0, note="mine",
        ))
        db.session.commit()

    resp = logged_in_client.get(f"/daily/{ds}")
    body = resp.data.decode()
    assert "NOT MINE" not in body
    assert "mine" in body
    assert "$50.00" in body
