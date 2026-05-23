"""Monthly P&L invariant characterization tests.

Pins the contracts documented in
`api/Modules/Monthly/INVARIANTS.md`. These tests are deliberately
boring — they read like the doc reads. The point is that breaking
an invariant by accident breaks one of these in CI.

Three sweeps:
  1. **422-trap**: parametrized over every read-only field on the
     monthly PUT — each one rejected by `extra="forbid"`.
  2. **Bedrock formula**: `total_income`, `total_expenses`,
     `net_profit` pinned to the documented math.
  3. **Daily-derived auto-fill**: parametrized over the
     `_DAILY_DERIVED_FIELDS` mapping — each monthly column equals
     the sum of its corresponding daily column over the month.

If you change any of these, change the doc + the test together.
"""
from datetime import date

import pytest

from tests._app import db, db_session


# ── Helpers ──────────────────────────────────────────────────


def _admin_jwt(client, store_id):
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


def _seed_daily(store_id, report_date, **fields):
    from api.Modules.DailyBook.Models import DailyReport
    with db_session():
        db.session.add(DailyReport(
            store_id=store_id, report_date=report_date, **fields,
        ))
        db.session.commit()


# ── 1. The 422 trap ──────────────────────────────────────────
#
# Every field in this list is read-only on the PUT. The schema
# rejects the WHOLE payload (not just the offending field) so a
# stale or hostile client gets a clear error.
#
# Includes:
#  - Category 2 (daily-derived): cash_purchases, check_purchases,
#    cash_expenses, check_expenses, cash_payroll, check_cashing_fees
#  - Category 3 (cross-table): return_check_gl
#  - Legacy split columns: bank_charges_210, bank_charges_230
#  - DB-managed: id, store_id, year, month, updated_at
#  - Computed totals: total_income, total_expenses, net_profit


READ_ONLY_FIELDS = [
    # Daily-derived (Category 2)
    "cash_purchases",
    "check_purchases",
    "cash_expenses",
    "check_expenses",
    "cash_payroll",
    "check_cashing_fees",
    # Cross-table-derived (Category 3 — return_check_gl is the only
    # one NOT in the schema; bank_charges_total IS in the schema)
    "return_check_gl",
    # Legacy bank-charge split — preserved on the model for historic
    # rows but never writable via this PUT
    "bank_charges_210",
    "bank_charges_230",
    # Database-managed
    "id",
    "store_id",
    "year",
    "month",
    "updated_at",
    # Computed totals (set by the controller adapter, not stored)
    "total_income",
    "total_expenses",
    "net_profit",
]


@pytest.mark.parametrize("forbidden_field", READ_ONLY_FIELDS)
def test_put_rejects_each_read_only_field(
    client, test_store_id, forbidden_field,
):
    """Every read-only field, sent on its own, triggers a 422.

    Pinned so accidentally exposing one of these on the request
    schema (e.g. by copy-pasting a column list) breaks CI rather
    than silently allowing client overwrites of the locked
    daily-ledger / bank-charge / return-check sums.
    """
    body = {forbidden_field: 1234}
    resp = _put_monthly(client, test_store_id, 2026, 1, body)
    assert resp.status_code == 422, (
        f"Expected 422 when PUT includes read-only field "
        f"{forbidden_field!r}, got {resp.status_code}: "
        f"{resp.get_data(as_text=True)}"
    )


def test_put_accepts_bank_charges_total_when_no_bank_sync():
    """`bank_charges_total` IS in the schema (unlike the other
    Category 3 field), so a PUT that includes it must NOT 422.

    Whether the value actually sticks is a separate contract
    (the controller honors the manual value only when no bank-
    sync data exists; covered elsewhere).
    """
    # Schema-level check only — exercise the Pydantic model
    # directly so we don't depend on test-client wiring here.
    from api.Modules.Monthly.Requests import MonthlyUpdateRequest

    body = MonthlyUpdateRequest.model_validate({"bank_charges_total": 42.0})
    assert body.bank_charges_total == 42.0


# ── 2. Bedrock formula characterization ─────────────────────


def test_total_income_pinned_to_documented_formula(client, test_store_id):
    """total_income sums the documented 12 income fields.

    Pinned with a non-trivial value per field (powers of 2 so a
    one-off bug is obvious in the failure delta).
    """
    income = {
        "taxable_sales":          1.0,
        "non_taxable":            2.0,
        "bill_payment_charge":    4.0,
        "phone_recargas":         8.0,
        "boost_mobile":          16.0,
        # check_cashing_fees comes from the daily ledger
        "return_check_hold_fees": 64.0,
        "rebates_commissions":  128.0,
        "mt_commission_in_bank": 256.0,
        "other_income_1":       512.0,
        "other_income_2":      1024.0,
        "other_income_3":      2048.0,
    }
    resp = _put_monthly(client, test_store_id, 2026, 10, income)
    assert resp.status_code == 200, resp.get_data(as_text=True)
    body = resp.get_json()["report"]
    # 1+2+4+8+16+64+128+256+512+1024+2048 = 4063
    # (check_cashing_fees stays 0 — no daily seeded)
    expected = 1 + 2 + 4 + 8 + 16 + 64 + 128 + 256 + 512 + 1024 + 2048
    assert body["total_income"] == float(expected)


def test_total_expenses_pinned_to_documented_formula(client, test_store_id):
    """total_expenses sums the documented 19 expense + adjustment
    fields. over_short, borrowed_money_return, profit_distributed
    are all in the expense bucket (legacy P&L convention)."""
    expenses = {
        # Operator-editable expenses
        "credit_card_fees":         1.0,
        "money_order_rent":         2.0,
        "emaginenet_tech":          4.0,
        "irs_payroll_tax":          8.0,
        "texas_workforce":         16.0,
        "other_taxes":             32.0,
        "accounting_charges":      64.0,
        "other_expense_1":        128.0,
        "other_expense_2":        256.0,
        "other_expense_3":        512.0,
        "other_expense_4":       1024.0,
        "other_expense_5":       2048.0,
        # End-of-month adjustments (bucketed as expenses)
        "over_short":            4096.0,
        "borrowed_money_return": 8192.0,
        "profit_distributed":   16384.0,
        # bank_charges_total is in the schema; honored because no
        # bank-sync data exists for this month
        "bank_charges_total":      32.0,
    }
    resp = _put_monthly(client, test_store_id, 2026, 11, expenses)
    assert resp.status_code == 200, resp.get_data(as_text=True)
    body = resp.get_json()["report"]
    expected = sum(expenses.values())
    assert body["total_expenses"] == float(expected)


def test_net_profit_is_income_minus_expenses(client, test_store_id):
    """net_profit = total_income - total_expenses, full stop."""
    body = {
        "taxable_sales":  1000.0,
        "non_taxable":     500.0,
        "credit_card_fees": 50.0,
        "money_order_rent": 25.0,
        "over_short":       10.0,
    }
    resp = _put_monthly(client, test_store_id, 2026, 12, body)
    assert resp.status_code == 200
    r = resp.get_json()["report"]
    assert r["total_income"]   == 1500.0
    assert r["total_expenses"] ==   85.0
    assert r["net_profit"]     == 1415.0


# ── 3. Daily-derived auto-fill sweep ────────────────────────
#
# Parametrize over the `_DAILY_DERIVED_FIELDS` mapping (the
# canonical registry in `Services/write.py`) so adding a new
# auto-derived field just requires extending the registry +
# this list — the test infrastructure stays the same.


DAILY_DERIVED = [
    # (monthly_field,         daily_field,         seed values)
    ("cash_purchases",        "cash_purchases",    (12.50, 37.50)),
    ("check_purchases",       "check_purchases",   (100.00, 50.00)),
    ("cash_expenses",         "cash_expense",      (5.25, 15.75)),
    ("check_expenses",        "check_expense",     (200.00, 100.00)),
    ("cash_payroll",          "payroll_expense",   (1000.00, 500.00)),
    ("check_cashing_fees",    "check_cashing_fees",(2.50, 7.50)),
]


@pytest.mark.parametrize(
    "monthly_field,daily_field,seeds", DAILY_DERIVED,
    ids=[m for (m, _, _) in DAILY_DERIVED],
)
def test_daily_derived_field_sums_from_ledger(
    client, test_store_id, monthly_field, daily_field, seeds,
):
    """Every Category-2 field equals the sum of its DailyReport
    column over the month. Pinned per-field so a typo in
    `_DAILY_DERIVED_FIELDS` (e.g. an off-by-one on the daily
    column name) shows up as a per-field assertion failure, not a
    cryptic aggregate mismatch."""
    from api.Modules.Monthly.Models import MonthlyFinancial
    # Pick a unique month per parametrize case so the rows don't
    # collide with sibling tests in the same store fixture.
    month = 1 + DAILY_DERIVED.index(
        (monthly_field, daily_field, seeds),
    )
    y = 2030  # well away from the controller test fixtures

    _seed_daily(test_store_id, date(y, month, 5), **{daily_field: seeds[0]})
    _seed_daily(test_store_id, date(y, month, 20), **{daily_field: seeds[1]})

    resp = _put_monthly(client, test_store_id, y, month, {"notes": ""})
    assert resp.status_code == 200, resp.get_data(as_text=True)

    expected = round(seeds[0] + seeds[1], 2)
    with db_session():
        row = db.session.query(MonthlyFinancial).filter_by(
            store_id=test_store_id, year=y, month=month,
        ).first()
        actual = float(getattr(row, monthly_field))
        assert abs(actual - expected) < 0.01, (
            f"{monthly_field!r} expected {expected}, got {actual} "
            f"(daily column: {daily_field!r})"
        )


# ── 4. Bank-charges conditional-lock contract ───────────────


def test_bank_charges_total_honors_manual_when_no_sync(client, test_store_id):
    """Stores without bank-sync data: operator's typed value wins.

    This is the Basic-plan path. Unconditionally locking the field
    would wipe their manual entries on every save — covered by
    this test so a "simplification" of `update_monthly` can't
    silently break Basic-plan stores.
    """
    from api.Modules.Monthly.Models import MonthlyFinancial
    resp = _put_monthly(client, test_store_id, 2031, 3, {
        "bank_charges_total": 87.50,
    })
    assert resp.status_code == 200
    with db_session():
        row = db.session.query(MonthlyFinancial).filter_by(
            store_id=test_store_id, year=2031, month=3,
        ).first()
        assert abs(float(row.bank_charges_total) - 87.50) < 0.01


# ── 5. Empty-PUT contract ───────────────────────────────────


def test_empty_put_creates_row_with_zeros_and_locked_field_refresh(
    client, test_store_id,
):
    """An empty PUT body is the documented "re-roll the locked
    fields without changing anything else" pattern. Verify it
    creates the row on first call AND that the locked fields are
    populated from the daily ledger."""
    from api.Modules.Monthly.Models import MonthlyFinancial
    y, m = 2032, 2
    _seed_daily(test_store_id, date(y, m, 10), cash_purchases=42.0)

    # An empty payload still satisfies the schema (every numeric
    # field defaults to None, notes defaults to "").
    resp = _put_monthly(client, test_store_id, y, m, {})
    assert resp.status_code == 200, resp.get_data(as_text=True)

    with db_session():
        row = db.session.query(MonthlyFinancial).filter_by(
            store_id=test_store_id, year=y, month=m,
        ).first()
        assert row is not None
        # Daily-derived locked field refreshed from the ledger
        assert abs(float(row.cash_purchases) - 42.0) < 0.01
        # Operator-editable field defaults to 0
        assert float(row.taxable_sales) == 0.0
