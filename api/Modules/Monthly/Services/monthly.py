"""Monthly P&L service.

Computes total_income, total_expenses, and net_profit for a
MonthlyFinancial row so the SPA controller doesn't have to
duplicate the math (and the same totals power the legacy
template).
"""
from dataclasses import dataclass

from sqlalchemy.orm import Session

from api.Modules.Monthly.Models import MonthlyFinancial
from api.Modules.Monthly.Repositories import find_monthly_for


# Field categorisation. Same buckets as the legacy template's
# Total Income / Total Expenses headers — single source.
INCOME_FIELDS: tuple[str, ...] = (
    "taxable_sales", "non_taxable",
    "bill_payment_charge", "phone_recargas", "boost_mobile",
    "check_cashing_fees", "return_check_hold_fees",
    "rebates_commissions", "mt_commission_in_bank",
    "other_income_1", "other_income_2", "other_income_3",
)
EXPENSE_FIELDS: tuple[str, ...] = (
    "cash_purchases", "check_purchases",
    "cash_expenses", "check_expenses", "cash_payroll",
    "check_payroll",
    "bank_charges_total", "credit_card_fees",
    "money_order_rent", "emaginenet_tech",
    "irs_payroll_tax", "texas_workforce", "other_taxes",
    "accounting_charges", "return_check_gl",
    "other_expense_1", "other_expense_2", "other_expense_3",
    "other_expense_4", "other_expense_5",
    "over_short", "borrowed_money_return", "profit_distributed",
)


@dataclass
class MonthlySummary:
    """Service-layer DTO. The Controller converts this into the
    Pydantic response model."""
    row: MonthlyFinancial
    total_income: float
    total_expenses: float

    @property
    def net_profit(self) -> float:
        return round(self.total_income - self.total_expenses, 2)


def _sum_fields(row: MonthlyFinancial, fields: tuple[str, ...]) -> float:
    total = 0.0
    for f in fields:
        v = getattr(row, f, 0) or 0
        total += float(v)
    return round(total, 2)


def summarize_monthly(
    db: Session, store_id: int, year: int, month: int,
) -> MonthlySummary | None:
    """Return a MonthlySummary for the (store, year, month) or
    None when no row has been logged for that month."""
    row = find_monthly_for(db, store_id, year, month)
    if row is None:
        return None
    return MonthlySummary(
        row=row,
        total_income=_sum_fields(row, INCOME_FIELDS),
        total_expenses=_sum_fields(row, EXPENSE_FIELDS),
    )
