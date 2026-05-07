"""Period P&L report aggregator.

Aggregates `DailyReport` rows in the chosen period into income /
expense lines, plus money-transfer fees from `Transfer`. The result
is a daily-book P&L over an arbitrary date range — it does NOT
include `MonthlyFinancial` manual fields like credit_card_fees /
accounting_charges, since those are per-month entries that don't
decompose to a date range.

Pure DB read — no commits, no side-effects.
"""
from datetime import date

from sqlalchemy import func
from sqlalchemy.orm import Session

from api.Modules.Reports.Services.period_comparison import (
    PL_EXPENSE_LINES,
    PL_INCOME_LINES,
)


def period_pl(
    db: Session,
    store_ids: list[int],
    d_from: date,
    d_to: date,
) -> tuple[list[dict], dict]:
    """Build the period P&L rows + totals.

    Returns `(rows, totals)`:
      - rows: one dict per line item with `label`, `section`,
        `amount`. Sections are `"Income"` or `"Expenses"`. The order
        is: PL_INCOME_LINES → "Money Transfer Fees" → PL_EXPENSE_LINES.
      - totals: `income`, `expenses`, `net`, `days`. `days` is the
        number of `DailyReport` rows in the window (NOT the date span).
    """
    from app import DailyReport, Transfer
    from api.Modules.Reports.Repositories.transfers import period_filters

    daily = (
        db.query(DailyReport)
          .filter(
              DailyReport.store_id.in_(store_ids),
              DailyReport.report_date >= d_from,
              DailyReport.report_date <= d_to,
          )
          .all()
    )
    fee_total = (
        db.query(func.coalesce(func.sum(Transfer.fee), 0.0))
          .filter(*period_filters(store_ids, d_from, d_to))
          .scalar()
    ) or 0.0

    rows: list[dict] = []
    income_total = 0.0
    for label, attr in PL_INCOME_LINES:
        v = sum(float(getattr(r, attr) or 0.0) for r in daily)
        rows.append({"label": label, "section": "Income", "amount": v})
        income_total += v
    rows.append({
        "label": "Money Transfer Fees",
        "section": "Income",
        "amount": float(fee_total),
    })
    income_total += float(fee_total)

    expense_total = 0.0
    for label, attr in PL_EXPENSE_LINES:
        v = sum(float(getattr(r, attr) or 0.0) for r in daily)
        rows.append({"label": label, "section": "Expenses", "amount": v})
        expense_total += v

    totals = {
        "income":   income_total,
        "expenses": expense_total,
        "net":      income_total - expense_total,
        "days":     len(daily),
    }
    return rows, totals
