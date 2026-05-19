"""Monthly — Models.

* ``MonthlyFinancial`` — one row per (store, year, month). Carries
                          the P&L line items: revenue, purchases,
                          expenses, write-offs, and the over/short +
                          cash-carry adjustments that close the month.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Column, DateTime, Float, ForeignKey, Integer, Text, UniqueConstraint,
)

from api.Core.Database import Base


class MonthlyFinancial(Base):
    __tablename__ = "monthly_financial"
    id                    = Column(Integer, primary_key=True)
    store_id              = Column(Integer, ForeignKey("store.id"), nullable=False)
    year                  = Column(Integer, nullable=False)
    month                 = Column(Integer, nullable=False)
    taxable_sales         = Column(Float, default=0.0)
    non_taxable           = Column(Float, default=0.0)
    bill_payment_charge   = Column(Float, default=0.0)
    phone_recargas        = Column(Float, default=0.0)
    boost_mobile          = Column(Float, default=0.0)
    check_cashing_fees    = Column(Float, default=0.0)
    return_check_hold_fees= Column(Float, default=0.0)
    rebates_commissions   = Column(Float, default=0.0)
    mt_commission_in_bank = Column(Float, default=0.0)
    other_income_1        = Column(Float, default=0.0)
    other_income_2        = Column(Float, default=0.0)
    other_income_3        = Column(Float, default=0.0)
    cash_purchases        = Column(Float, default=0.0)
    check_purchases       = Column(Float, default=0.0)
    cash_expenses         = Column(Float, default=0.0)
    check_expenses        = Column(Float, default=0.0)
    cash_payroll          = Column(Float, default=0.0)
    bank_charges_210      = Column(Float, default=0.0)
    bank_charges_230      = Column(Float, default=0.0)
    # Single consolidated bank-charges line, fed by the bank-sync
    # registry. The 210/230 split above is preserved for historic
    # rows but no longer rendered separately on the P&L UI.
    bank_charges_total    = Column(Float, default=0.0)
    credit_card_fees      = Column(Float, default=0.0)
    money_order_rent      = Column(Float, default=0.0)
    emaginenet_tech       = Column(Float, default=0.0)
    irs_payroll_tax       = Column(Float, default=0.0)
    texas_workforce       = Column(Float, default=0.0)
    other_taxes           = Column(Float, default=0.0)
    accounting_charges    = Column(Float, default=0.0)
    return_check_gl       = Column(Float, default=0.0)
    other_expense_1       = Column(Float, default=0.0)
    other_expense_2       = Column(Float, default=0.0)
    other_expense_3       = Column(Float, default=0.0)
    other_expense_4       = Column(Float, default=0.0)
    other_expense_5       = Column(Float, default=0.0)
    over_short            = Column(Float, default=0.0)
    borrowed_money_return = Column(Float, default=0.0)
    profit_distributed    = Column(Float, default=0.0)
    cash_carry_forward    = Column(Float, default=0.0)
    notes                 = Column(Text, default="")
    updated_at            = Column(DateTime, default=datetime.utcnow)
    __table_args__ = (UniqueConstraint("store_id", "year", "month"),)

    @property
    def total_revenue(self) -> float:
        return float(sum([
            self.taxable_sales, self.non_taxable, self.bill_payment_charge,
            self.phone_recargas, self.boost_mobile, self.check_cashing_fees,
            self.return_check_hold_fees, self.rebates_commissions,
            self.mt_commission_in_bank, self.other_income_1,
            self.other_income_2, self.other_income_3,
        ]))

    @property
    def total_purchases(self) -> float:
        return float(self.cash_purchases + self.check_purchases)

    @property
    def total_expenses(self) -> float:
        return float(sum([
            self.cash_expenses, self.check_expenses, self.cash_payroll,
            self.bank_charges_210, self.bank_charges_230,
            self.credit_card_fees, self.money_order_rent,
            self.emaginenet_tech, self.irs_payroll_tax,
            self.texas_workforce, self.other_taxes, self.accounting_charges,
            self.return_check_gl, self.other_expense_1, self.other_expense_2,
            self.other_expense_3, self.other_expense_4, self.other_expense_5,
        ]))

    @property
    def net_income(self) -> float:
        return float(self.total_revenue - self.total_purchases
                     - self.total_expenses + self.over_short)


__all__ = ["MonthlyFinancial"]
