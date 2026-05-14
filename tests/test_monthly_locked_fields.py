"""Tests for the read-only daily-book-derived fields on the Monthly P&L.

`cash_purchases`, `check_purchases`, `cash_expenses`, `check_expenses`,
`cash_payroll`, and `check_cashing_fees` are sums of DailyReport rows
for the month. The Monthly P&L editor moved to React in PR #402; the
SPA PUTs to `/api/v2/monthly/<year>/<month>` (`MonthlyUpdateRequest`
with `extra="forbid"` rejecting the auto-derived fields outright)
and the server overwrites them from the daily ledger on save.

Two contracts pinned here:
  - **Auto-derive on save**: PUT without sending the locked fields →
    server populates them from the daily ledger. The `auto_*` test
    keeps the daily-sum invariant honest.
  - **Reject tampering**: PUT *with* a locked field in the body →
    422 from the Pydantic schema. The legacy /monthly form silently
    overwrote tampered values; the new API rejects the whole payload
    so a stale or hostile client gets a clear error instead of a
    silent ignore.
"""
from datetime import date

from tests._app import db, db_session


def _seed_daily_report(store_id, report_date, **fields):
    """Drop a DailyReport row with the given daily-book numbers."""
    from api.Modules.DailyBook.Models import DailyReport
    with db_session():
        r = DailyReport(store_id=store_id, report_date=report_date, **fields)
        db.session.add(r)
        db.session.commit()


def _admin_jwt(client, store_id):
    """Mint a Bearer JWT for the seeded admin so /api/v2/monthly/*
    accepts the call."""
    resp = client.post(
        "/api/v2/auth/login",
        json={"username": "admin@test.com",
              "password": "testpass123!",
              "store_id": store_id},
    )
    return resp.get_json()["access_token"]


def _put_monthly(client, store_id, year, month, body):
    token = _admin_jwt(client, store_id)
    return client.put(
        f"/api/v2/monthly/{year}/{month}",
        json=body,
        headers={"Authorization": f"Bearer {token}"},
    )


# ── Auto-derive on save ──────────────────────────────────────


def test_locked_fields_populate_from_daily_sums_on_save(client, test_store_id):
    """PUT a notes-only payload → server must populate the five
    daily-derived fields from the DailyReport rows for the month."""
    from api.Modules.Monthly.Models import MonthlyFinancial
    y, m = 2026, 4
    _seed_daily_report(test_store_id, date(y, m, 3),
                       cash_purchases=100.0, check_purchases=50.0,
                       cash_expense=25.0, check_expense=15.0, payroll_expense=200.0)
    _seed_daily_report(test_store_id, date(y, m, 17),
                       cash_purchases=75.0, check_purchases=20.0,
                       cash_expense=10.0, check_expense=8.0, payroll_expense=150.0)
    resp = _put_monthly(client, test_store_id, y, m, {"notes": "first save"})
    assert resp.status_code == 200, resp.get_data(as_text=True)
    with db_session():
        r = db.session.query(MonthlyFinancial).filter_by(
            store_id=test_store_id, year=y, month=m).first()
        assert r is not None
        assert abs(r.cash_purchases  - 175.0) < 0.01
        assert abs(r.check_purchases -  70.0) < 0.01
        assert abs(r.cash_expenses   -  35.0) < 0.01
        assert abs(r.check_expenses  -  23.0) < 0.01
        assert abs(r.cash_payroll    - 350.0) < 0.01


def test_check_cashing_fees_auto_populates(client, test_store_id):
    """Same daily-derived contract for check_cashing_fees."""
    from api.Modules.Monthly.Models import MonthlyFinancial
    y, m = 2026, 8
    _seed_daily_report(test_store_id, date(y, m, 4),  check_cashing_fees=12.50)
    _seed_daily_report(test_store_id, date(y, m, 19), check_cashing_fees=37.75)
    resp = _put_monthly(client, test_store_id, y, m, {"notes": ""})
    assert resp.status_code == 200
    with db_session():
        r = db.session.query(MonthlyFinancial).filter_by(
            store_id=test_store_id, year=y, month=m).first()
        assert abs(r.check_cashing_fees - 50.25) < 0.01


# ── Reject tampering (extra="forbid") ────────────────────────


def test_tampered_locked_field_rejected_with_422(client, test_store_id):
    """The /api/v2/monthly PUT body schema has extra='forbid', so a
    payload that includes any of the auto-derived fields is rejected
    outright. This is a stronger guarantee than the legacy form,
    which silently overwrote tampered values — clients get a clear
    422 instead of a silent ignore."""
    y, m = 2026, 5
    _seed_daily_report(test_store_id, date(y, m, 10),
                       cash_purchases=200.0, check_purchases=60.0,
                       cash_expense=40.0, check_expense=12.0, payroll_expense=500.0)
    resp = _put_monthly(client, test_store_id, y, m, {
        "cash_purchases": 99999,
        "check_purchases": 99999,
        "cash_expenses":   99999,
        "check_expenses":  99999,
        "cash_payroll":    99999,
    })
    assert resp.status_code == 422


def test_tampered_check_cashing_fees_rejected_with_422(client, test_store_id):
    """check_cashing_fees is locked the same way as the COGS/expense
    fields — also rejected by `extra='forbid'`."""
    y, m = 2026, 9
    _seed_daily_report(test_store_id, date(y, m, 11), check_cashing_fees=42.00)
    resp = _put_monthly(client, test_store_id, y, m, {
        "check_cashing_fees": 99999,
    })
    assert resp.status_code == 422


# ── Unlocked fields still accept submitted values ───────────


def test_unlocked_fields_save_submitted_values(client, test_store_id):
    """The lock is scoped to the daily-derived fields. Manually-
    entered fields (mt_commission_in_bank, other_income_1, etc.)
    take whatever the user typed."""
    from api.Modules.Monthly.Models import MonthlyFinancial
    y, m = 2026, 6
    resp = _put_monthly(client, test_store_id, y, m, {
        "mt_commission_in_bank": 250.0,
        "other_income_1":         33.0,
    })
    assert resp.status_code == 200
    with db_session():
        r = db.session.query(MonthlyFinancial).filter_by(
            store_id=test_store_id, year=y, month=m).first()
        assert abs(r.mt_commission_in_bank - 250.0) < 0.01
        assert abs(r.other_income_1 - 33.0) < 0.01


# ── Refresh on resave: locked fields track current daily sum ────


def test_resaving_picks_up_fresh_daily_sums(client, test_store_id):
    """After saving a P&L, if admin edits a daily book row, the
    next save should reflect the NEW sum rather than whatever was
    stored. The locked-field contract is "always trust the daily
    ledger, never the stored MonthlyFinancial value"."""
    from api.Modules.DailyBook.Models import DailyReport
    from api.Modules.Monthly.Models import MonthlyFinancial
    y, m = 2026, 7
    _seed_daily_report(test_store_id, date(y, m, 5), cash_expense=100.0)
    _put_monthly(client, test_store_id, y, m, {"notes": ""})
    # Admin edits the daily book — cash_expense jumps to 250.
    with db_session():
        r = db.session.query(DailyReport).filter_by(
            store_id=test_store_id, report_date=date(y, m, 5)).first()
        r.cash_expense = 250.0
        db.session.commit()
    # Re-save the monthly report — the locked field reflects the
    # fresh daily sum, NOT the stored MonthlyFinancial.cash_expenses.
    resp = _put_monthly(client, test_store_id, y, m, {"notes": "resaved"})
    assert resp.status_code == 200
    with db_session():
        row = db.session.query(MonthlyFinancial).filter_by(
            store_id=test_store_id, year=y, month=m).first()
        assert abs(row.cash_expenses - 250.0) < 0.01
