"""Monthly — Models.

* ``MonthlyFinancial`` — one row per (store, year, month). Carries
                          the P&L line items: revenue, purchases,
                          expenses, write-offs, and the over/short +
                          cash-carry adjustments that close the month.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger, Column, DateTime, ForeignKey, Integer, Text,
    UniqueConstraint,
)

from api.Core.Database import Base
from api.Core.Money import DollarView, to_dollars


class MonthlyFinancial(Base):
    __tablename__ = "msb_monthly_financial"
    id                    = Column(Integer, primary_key=True)
    store_id              = Column(Integer, ForeignKey("tenancy_store.id"), nullable=False)
    year                  = Column(Integer, nullable=False)
    month                 = Column(Integer, nullable=False)
    taxable_sales_cents   = Column(BigInteger, default=0)
    non_taxable_cents     = Column(BigInteger, default=0)
    bill_payment_charge_cents = Column(BigInteger, default=0)
    phone_recargas_cents  = Column(BigInteger, default=0)
    boost_mobile_cents    = Column(BigInteger, default=0)
    check_cashing_fees_cents = Column(BigInteger, default=0)
    return_check_hold_fees_cents = Column(BigInteger, default=0)
    rebates_commissions_cents = Column(BigInteger, default=0)
    mt_commission_in_bank_cents = Column(BigInteger, default=0)
    other_income_1_cents  = Column(BigInteger, default=0)
    other_income_2_cents  = Column(BigInteger, default=0)
    other_income_3_cents  = Column(BigInteger, default=0)
    cash_purchases_cents  = Column(BigInteger, default=0)
    check_purchases_cents = Column(BigInteger, default=0)
    cash_expenses_cents   = Column(BigInteger, default=0)
    check_expenses_cents  = Column(BigInteger, default=0)
    cash_payroll_cents    = Column(BigInteger, default=0)
    # Payroll paid by CHECK — daily-derived from
    # DailyReport.payroll_check (which the daily book's own totals
    # deliberately ignore; checks don't move drawer cash).
    check_payroll_cents   = Column(BigInteger, default=0)
    bank_charges_210_cents = Column(BigInteger, default=0)
    bank_charges_230_cents = Column(BigInteger, default=0)
    # Single consolidated bank-charges line, fed by the bank-sync
    # registry. The 210/230 split above is preserved for historic
    # rows but no longer rendered separately on the P&L UI.
    bank_charges_total_cents = Column(BigInteger, default=0)
    credit_card_fees_cents = Column(BigInteger, default=0)
    money_order_rent_cents = Column(BigInteger, default=0)
    emaginenet_tech_cents = Column(BigInteger, default=0)
    irs_payroll_tax_cents = Column(BigInteger, default=0)
    texas_workforce_cents = Column(BigInteger, default=0)
    other_taxes_cents     = Column(BigInteger, default=0)
    accounting_charges_cents = Column(BigInteger, default=0)
    return_check_gl_cents = Column(BigInteger, default=0)
    other_expense_1_cents = Column(BigInteger, default=0)
    other_expense_2_cents = Column(BigInteger, default=0)
    other_expense_3_cents = Column(BigInteger, default=0)
    other_expense_4_cents = Column(BigInteger, default=0)
    other_expense_5_cents = Column(BigInteger, default=0)
    over_short_cents      = Column(BigInteger, default=0)
    borrowed_money_return_cents = Column(BigInteger, default=0)
    profit_distributed_cents = Column(BigInteger, default=0)
    cash_carry_forward_cents = Column(BigInteger, default=0)
    notes                 = Column(Text, default="")
    updated_at            = Column(DateTime, default=datetime.utcnow)
    __table_args__ = (UniqueConstraint("store_id", "year", "month"),)

    # Money is stored as INTEGER CENTS (P0-3; see api/Core/Money.py
    # and DailyBook/Models for the pattern).
    taxable_sales = DollarView("taxable_sales_cents")
    non_taxable = DollarView("non_taxable_cents")
    bill_payment_charge = DollarView("bill_payment_charge_cents")
    phone_recargas = DollarView("phone_recargas_cents")
    boost_mobile = DollarView("boost_mobile_cents")
    check_cashing_fees = DollarView("check_cashing_fees_cents")
    return_check_hold_fees = DollarView("return_check_hold_fees_cents")
    rebates_commissions = DollarView("rebates_commissions_cents")
    mt_commission_in_bank = DollarView("mt_commission_in_bank_cents")
    other_income_1 = DollarView("other_income_1_cents")
    other_income_2 = DollarView("other_income_2_cents")
    other_income_3 = DollarView("other_income_3_cents")
    cash_purchases = DollarView("cash_purchases_cents")
    check_purchases = DollarView("check_purchases_cents")
    cash_expenses = DollarView("cash_expenses_cents")
    check_expenses = DollarView("check_expenses_cents")
    cash_payroll = DollarView("cash_payroll_cents")
    check_payroll = DollarView("check_payroll_cents")
    bank_charges_210 = DollarView("bank_charges_210_cents")
    bank_charges_230 = DollarView("bank_charges_230_cents")
    bank_charges_total = DollarView("bank_charges_total_cents")
    credit_card_fees = DollarView("credit_card_fees_cents")
    money_order_rent = DollarView("money_order_rent_cents")
    emaginenet_tech = DollarView("emaginenet_tech_cents")
    irs_payroll_tax = DollarView("irs_payroll_tax_cents")
    texas_workforce = DollarView("texas_workforce_cents")
    other_taxes = DollarView("other_taxes_cents")
    accounting_charges = DollarView("accounting_charges_cents")
    return_check_gl = DollarView("return_check_gl_cents")
    other_expense_1 = DollarView("other_expense_1_cents")
    other_expense_2 = DollarView("other_expense_2_cents")
    other_expense_3 = DollarView("other_expense_3_cents")
    other_expense_4 = DollarView("other_expense_4_cents")
    other_expense_5 = DollarView("other_expense_5_cents")
    over_short = DollarView("over_short_cents")
    borrowed_money_return = DollarView("borrowed_money_return_cents")
    profit_distributed = DollarView("profit_distributed_cents")
    cash_carry_forward = DollarView("cash_carry_forward_cents")

    @property
    def total_revenue_cents(self) -> int:
        return int(sum(int(v or 0) for v in [
            self.taxable_sales_cents, self.non_taxable_cents,
            self.bill_payment_charge_cents, self.phone_recargas_cents,
            self.boost_mobile_cents, self.check_cashing_fees_cents,
            self.return_check_hold_fees_cents,
            self.rebates_commissions_cents,
            self.mt_commission_in_bank_cents, self.other_income_1_cents,
            self.other_income_2_cents, self.other_income_3_cents,
        ]))

    @property
    def total_revenue(self) -> float:
        return to_dollars(self.total_revenue_cents)

    @property
    def total_purchases_cents(self) -> int:
        return int(self.cash_purchases_cents or 0) + int(
            self.check_purchases_cents or 0)

    @property
    def total_purchases(self) -> float:
        return to_dollars(self.total_purchases_cents)

    @property
    def total_expenses_cents(self) -> int:
        return int(sum(int(v or 0) for v in [
            self.cash_expenses_cents, self.check_expenses_cents,
            self.cash_payroll_cents, self.check_payroll_cents,
            self.bank_charges_210_cents, self.bank_charges_230_cents,
            self.credit_card_fees_cents, self.money_order_rent_cents,
            self.emaginenet_tech_cents, self.irs_payroll_tax_cents,
            self.texas_workforce_cents, self.other_taxes_cents,
            self.accounting_charges_cents, self.return_check_gl_cents,
            self.other_expense_1_cents, self.other_expense_2_cents,
            self.other_expense_3_cents, self.other_expense_4_cents,
            self.other_expense_5_cents,
        ]))

    @property
    def total_expenses(self) -> float:
        return to_dollars(self.total_expenses_cents)

    @property
    def net_income_cents(self) -> int:
        return int(
            self.total_revenue_cents - self.total_purchases_cents
            - self.total_expenses_cents + int(self.over_short_cents or 0)
        )

    @property
    def net_income(self) -> float:
        return to_dollars(self.net_income_cents)


__all__ = ["MonthlyFinancial"]
