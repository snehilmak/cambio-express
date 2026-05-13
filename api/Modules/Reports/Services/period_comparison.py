"""Period comparison report aggregator.

Compares the chosen period against another period:
  - default: immediately-prior period of the same length
  - custom: pass `compare_from` / `compare_to` for arbitrary
    windows (e.g. "this month vs. same month last year")

Returns rows for Transfers / Total Sent / Fees / Federal Tax /
Total Income / Total Expenses / Net Income, each with current
+ prior + delta + pct.

Pure DB read — no commits, no side-effects.
"""
from datetime import date, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session


# Daily-book P&L line items. Income lines flow from `DailyReport`
# columns + the period's transfer fees. Expense lines flow from
# `DailyReport` columns. The MonthlyFinancial manual fields
# (credit_card_fees, accounting_charges) are NOT included — those
# are per-month entries that don't decompose to an arbitrary
# date range.
PL_INCOME_LINES: list[tuple[str, str]] = [
    ("Taxable Sales",          "taxable_sales"),
    ("Non-Taxable Sales",      "non_taxable"),
    ("Bill Payment Charges",   "bill_payment_charge"),
    ("Phone Recargas",         "phone_recargas"),
    ("Boost Mobile",           "boost_mobile"),
    ("Check Cashing Fees",     "check_cashing_fees"),
    ("Return Check Hold Fees", "return_check_hold_fees"),
    ("Rebates / Commissions",  "rebates_commissions"),
]
PL_EXPENSE_LINES: list[tuple[str, str]] = [
    ("Cash Purchases",  "cash_purchases"),
    ("Check Purchases", "check_purchases"),
    ("Cash Expenses",   "cash_expense"),
    ("Check Expenses",  "check_expense"),
    ("Cash Payroll",    "payroll_expense"),
]


def _bundle(db: Session, store_ids: list[int], s: date, e: date) -> dict:
    """Aggregate a single period into the metric dict the
    comparison view consumes."""
    from api.Modules.DailyBook.Models import DailyReport
    from api.Modules.Transfers.Models import Transfer
    from api.Modules.Reports.Repositories.transfers import (
        period_filters,
    )

    sent, fee_sum, tax_sum, count = (
        db.query(
            func.coalesce(func.sum(Transfer.send_amount), 0.0),
            func.coalesce(func.sum(Transfer.fee), 0.0),
            func.coalesce(func.sum(Transfer.federal_tax), 0.0),
            func.count(Transfer.id),
        )
        .filter(*period_filters(store_ids, s, e))
        .one()
    )
    daily = (
        db.query(DailyReport)
          .filter(
              DailyReport.store_id.in_(store_ids),
              DailyReport.report_date >= s,
              DailyReport.report_date <= e,
          )
          .all()
    )
    income = sum(
        float(getattr(r, a) or 0)
        for r in daily for _, a in PL_INCOME_LINES
    ) + float(fee_sum or 0)
    expenses = sum(
        float(getattr(r, a) or 0)
        for r in daily for _, a in PL_EXPENSE_LINES
    )
    return {
        "transfers":  int(count or 0),
        "send_total": float(sent or 0),
        "fees":       float(fee_sum or 0),
        "tax":        float(tax_sum or 0),
        "income":     income,
        "expenses":   expenses,
        "net":        income - expenses,
    }


def period_comparison(
    db: Session,
    store_ids: list[int],
    d_from: date,
    d_to: date,
    *,
    compare_from: date | None = None,
    compare_to: date | None = None,
) -> tuple[list[dict], dict]:
    """Compare the chosen period against another period.

    Defaults to the immediately-prior period of the same length
    when `compare_from` / `compare_to` aren't both provided.
    Pass arbitrary dates for a custom comparison.

    Returns `(rows, totals)`:
      - rows: per-metric dicts with `label`, `current`, `prior`,
        `delta`, `pct`, `is_money`. The metrics list is
        intentionally fixed so the template renders the same
        7-row table every time.
      - totals: `current_label` / `prior_label` strings for the
        column headers.
    """
    if compare_from and compare_to:
        prior_from, prior_to = compare_from, compare_to
        # Normalise if user picked them backwards.
        if prior_from > prior_to:
            prior_from, prior_to = prior_to, prior_from
    else:
        span = (d_to - d_from).days + 1
        prior_to = d_from - timedelta(days=1)
        prior_from = prior_to - timedelta(days=span - 1)

    cur = _bundle(db, store_ids, d_from, d_to)
    prior = _bundle(db, store_ids, prior_from, prior_to)

    metrics = [
        ("Transfers",      "transfers",  False),
        ("Total Sent",     "send_total", True),
        ("Fees Earned",    "fees",       True),
        ("Federal Tax",    "tax",        True),
        ("Total Income",   "income",     True),
        ("Total Expenses", "expenses",   True),
        ("Net Income",     "net",        True),
    ]
    rows = []
    for label, key, is_money in metrics:
        c = cur[key]
        p = prior[key]
        delta = c - p
        pct = (delta / p * 100.0) if p else (100.0 if c else 0.0)
        rows.append({
            "label":    label,
            "current":  c,
            "prior":    p,
            "delta":    delta,
            "pct":      pct,
            "is_money": is_money,
        })
    totals = {
        "current_label": (
            f"{d_from.strftime('%b %d')} – {d_to.strftime('%b %d, %Y')}"
        ),
        "prior_label": (
            f"{prior_from.strftime('%b %d')} – "
            f"{prior_to.strftime('%b %d, %Y')}"
        ),
    }
    return rows, totals
