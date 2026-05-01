"""Tests for the read-only daily-book-derived fields on the Monthly P&L.

Cash Purchases, Check Purchases, Cash Expenses, Check Expenses,
Cash Payroll, and Check Cashing Fees are all sums of DailyReport rows
for the month. They render readonly in the form AND the server forces
them to the auto sum on save — so a tampered POST (or a stale
submission after a daily-book edit) can't override the truth.
"""
from datetime import date
from app import app as flask_app, db


def _seed_daily_report(store_id, report_date, **fields):
    """Drop a DailyReport row with the given daily-book numbers."""
    from app import DailyReport
    with flask_app.app_context():
        r = DailyReport(store_id=store_id, report_date=report_date, **fields)
        db.session.add(r)
        db.session.commit()


def _post_monthly(logged_in_client, year, month, data):
    return logged_in_client.post(f"/monthly/{year}/{month}", data=data,
                                 follow_redirects=False)


# ── The five locked fields echo the monthly auto sum ──────────

def test_locked_fields_prefill_from_daily_sums(logged_in_client, test_store_id):
    """Without a saved MonthlyFinancial row, the GET page should show
    the daily-book sums inside the readonly inputs."""
    y, m = 2026, 4
    _seed_daily_report(test_store_id, date(y, m, 3),
                       cash_purchases=100.0, check_purchases=50.0,
                       cash_expense=25.0, check_expense=15.0, payroll_expense=200.0)
    _seed_daily_report(test_store_id, date(y, m, 17),
                       cash_purchases=75.0, check_purchases=20.0,
                       cash_expense=10.0, check_expense=8.0, payroll_expense=150.0)
    resp = logged_in_client.get(f"/monthly/{y}/{m}")
    assert resp.status_code == 200
    html = resp.data.decode()
    # Each locked field shows its auto sum + is rendered readonly.
    for name, total in [
        ("cash_purchases",  "175.00"),
        ("check_purchases", "70.00"),
        ("cash_expenses",   "35.00"),
        ("check_expenses",  "23.00"),
        ("cash_payroll",    "350.00"),
    ]:
        # The input appears with readonly attr and the right value.
        assert f'name="{name}"' in html
        assert f'value="{total}"' in html, f"locked field {name} missing value {total}"
    # "Locked" indicator text appears for at least one locked row.
    assert "Locked · sum of daily book" in html


# ── Server ignores tampered values for locked fields ──────────

def test_server_overrides_tampered_locked_fields(logged_in_client, test_store_id):
    """POST inflates every locked field to $99,999. The server must
    persist the daily-book sum instead, not the submitted value."""
    from app import MonthlyFinancial
    y, m = 2026, 5
    _seed_daily_report(test_store_id, date(y, m, 10),
                       cash_purchases=200.0, check_purchases=60.0,
                       cash_expense=40.0, check_expense=12.0, payroll_expense=500.0)
    tampered = {"cash_purchases": "99999", "check_purchases": "99999",
                "cash_expenses": "99999", "check_expenses": "99999",
                "cash_payroll": "99999"}
    resp = _post_monthly(logged_in_client, y, m, tampered)
    assert resp.status_code == 302   # redirects after save
    with flask_app.app_context():
        r = MonthlyFinancial.query.filter_by(
            store_id=test_store_id, year=y, month=m).first()
        assert r is not None
        assert abs(r.cash_purchases  - 200.0) < 0.01
        assert abs(r.check_purchases -  60.0) < 0.01
        assert abs(r.cash_expenses   -  40.0) < 0.01
        assert abs(r.check_expenses  -  12.0) < 0.01
        assert abs(r.cash_payroll    - 500.0) < 0.01


# ── Unlocked fields still accept form values ─────────────────

def test_unlocked_fields_still_save_submitted_values(logged_in_client, test_store_id):
    """The lock is scoped only to the five daily-derived fields.
    Manually-entered fields (mt_commission_in_bank, bank_charges_total,
    other_income_1, etc.) continue to take whatever the user typed."""
    from app import MonthlyFinancial
    y, m = 2026, 6
    resp = _post_monthly(logged_in_client, y, m, {
        "mt_commission_in_bank": "250",
        "bank_charges_total": "12.50",
        "other_income_1": "33",
    })
    assert resp.status_code == 302
    with flask_app.app_context():
        r = MonthlyFinancial.query.filter_by(
            store_id=test_store_id, year=y, month=m).first()
        assert abs(r.mt_commission_in_bank - 250.0) < 0.01
        assert abs(r.bank_charges_total - 12.5) < 0.01
        assert abs(r.other_income_1 - 33.0) < 0.01


# ── Check Cashing Fees: locked the same way as the COGS/expense fields ─
#
# Originally Check Cashing Fees was prefilled from the daily book but
# left editable, which let cashiers (or a stale form) inflate revenue
# on the P&L. Same treatment as the rest of the daily-derived fields:
# readonly UI + server forces the auto sum on save.

def test_check_cashing_fees_renders_readonly_with_daily_sum(logged_in_client, test_store_id):
    y, m = 2026, 8
    _seed_daily_report(test_store_id, date(y, m, 4),  check_cashing_fees=12.50)
    _seed_daily_report(test_store_id, date(y, m, 19), check_cashing_fees=37.75)
    resp = logged_in_client.get(f"/monthly/{y}/{m}")
    assert resp.status_code == 200
    html = resp.data.decode()
    assert 'name="check_cashing_fees"' in html
    assert 'value="50.25"' in html, "expected daily sum 50.25 in the readonly input"
    # Look for the readonly attr on the check_cashing_fees input — find
    # the input markup, then look at the surrounding window for `readonly`.
    idx = html.find('name="check_cashing_fees"')
    assert idx != -1
    # The readonly attr lives within the same <input> tag — bound a
    # small window forward to keep the assertion tight.
    nearby = html[idx:idx + 400]
    assert "readonly" in nearby, (
        "check_cashing_fees input must render readonly so it can't "
        "be hand-edited on the monthly P&L"
    )


def test_server_overrides_tampered_check_cashing_fees(logged_in_client, test_store_id):
    """Same anti-tamper guarantee as the other locked fields — the
    server must persist the daily-book sum, not the inflated POST."""
    from app import MonthlyFinancial
    y, m = 2026, 9
    _seed_daily_report(test_store_id, date(y, m, 11), check_cashing_fees=42.00)
    resp = _post_monthly(logged_in_client, y, m, {"check_cashing_fees": "99999"})
    assert resp.status_code == 302
    with flask_app.app_context():
        r = MonthlyFinancial.query.filter_by(
            store_id=test_store_id, year=y, month=m).first()
        assert r is not None
        assert abs(r.check_cashing_fees - 42.00) < 0.01, (
            f"server must ignore tampered check_cashing_fees POST and "
            f"use the daily sum (42.00); got {r.check_cashing_fees}"
        )


# ── Saved report still shows fresh daily sums, not stale values ──

def test_reopening_saved_report_refreshes_locked_fields(logged_in_client, test_store_id):
    """After saving a P&L, if admin edits a daily book row, the
    locked fields on the next GET should reflect the NEW sum rather
    than whatever was stored."""
    from app import DailyReport
    y, m = 2026, 7
    _seed_daily_report(test_store_id, date(y, m, 5), cash_expense=100.0)
    # Save the monthly report (auto grabs 100).
    _post_monthly(logged_in_client, y, m, {})
    # Now the admin edits the daily book — cash_expense jumps to 250.
    with flask_app.app_context():
        r = DailyReport.query.filter_by(
            store_id=test_store_id, report_date=date(y, m, 5)).first()
        r.cash_expense = 250.0
        db.session.commit()
    # Re-open the monthly report page — the locked field reflects
    # the fresh daily sum, NOT the stored MonthlyFinancial.cash_expenses.
    resp = logged_in_client.get(f"/monthly/{y}/{m}")
    html = resp.data.decode()
    assert 'value="250.00"' in html
