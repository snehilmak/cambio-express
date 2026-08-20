"""Pydantic schemas for the monthly P&L read-side."""
from pydantic import BaseModel, ConfigDict


class MonthlyRow(BaseModel):
    """One MonthlyFinancial row — the per-store, per-month P&L
    breakdown. Keep field names matching the model + legacy
    template so the SPA's table can be a generic key→value loop.
    """

    model_config = ConfigDict(extra="forbid")

    id: int
    store_id: int
    year: int
    month: int
    # Income side
    taxable_sales:          float = 0.0
    non_taxable:            float = 0.0
    bill_payment_charge:    float = 0.0
    phone_recargas:         float = 0.0
    boost_mobile:           float = 0.0
    check_cashing_fees:     float = 0.0
    return_check_hold_fees: float = 0.0
    rebates_commissions:    float = 0.0
    mt_commission_in_bank:  float = 0.0
    other_income_1:         float = 0.0
    other_income_2:         float = 0.0
    other_income_3:         float = 0.0
    # Expense side
    cash_purchases:         float = 0.0
    check_purchases:        float = 0.0
    cash_expenses:          float = 0.0
    check_expenses:         float = 0.0
    cash_payroll:           float = 0.0
    check_payroll:          float = 0.0
    bank_charges_total:     float = 0.0
    credit_card_fees:       float = 0.0
    money_order_rent:       float = 0.0
    emaginenet_tech:        float = 0.0
    irs_payroll_tax:        float = 0.0
    texas_workforce:        float = 0.0
    other_taxes:            float = 0.0
    accounting_charges:     float = 0.0
    return_check_gl:        float = 0.0
    other_expense_1:        float = 0.0
    other_expense_2:        float = 0.0
    other_expense_3:        float = 0.0
    other_expense_4:        float = 0.0
    other_expense_5:        float = 0.0
    over_short:             float = 0.0
    borrowed_money_return:  float = 0.0
    profit_distributed:     float = 0.0
    cash_carry_forward:     float = 0.0
    notes:                  str = ""
    # Computed totals — set by the controller adapter
    total_income:           float = 0.0
    total_expenses:         float = 0.0
    net_profit:             float = 0.0


class MonthlyResponse(BaseModel):
    """Wrapped single-month payload. `report` is None when no
    row exists for the (year, month) — clients distinguish via
    a 404 at the controller layer."""

    model_config = ConfigDict(extra="forbid")

    report: MonthlyRow


class MonthLogged(BaseModel):
    """One (year, month) entry the store has logged."""

    model_config = ConfigDict(extra="forbid")

    year: int
    month: int


class MonthsLoggedResponse(BaseModel):
    """Wrapped list of all (year, month) pairs with rows.
    Sorted newest-first so the SPA can default to the most
    recent."""

    model_config = ConfigDict(extra="forbid")

    months: list[MonthLogged]


class MonthlyUpdateRequest(BaseModel):
    """PUT body for /monthly/{year}/{month}.

    All numeric fields optional — the SPA can submit only what
    the operator edited. Auto-derived fields (cash_purchases,
    cash_expenses, return_check_gl, bank_charges_total when
    bank-sync data exists, etc.) are NOT in this schema; the
    server overwrites them from the daily ledger / bank
    transactions / return-check workflow regardless of what the
    client sends.
    """

    model_config = ConfigDict(extra="forbid")

    taxable_sales:           float | None = None
    non_taxable:             float | None = None
    bill_payment_charge:     float | None = None
    phone_recargas:          float | None = None
    boost_mobile:            float | None = None
    return_check_hold_fees:  float | None = None
    rebates_commissions:     float | None = None
    mt_commission_in_bank:   float | None = None
    other_income_1:          float | None = None
    other_income_2:          float | None = None
    other_income_3:          float | None = None
    bank_charges_total:      float | None = None
    credit_card_fees:        float | None = None
    money_order_rent:        float | None = None
    emaginenet_tech:         float | None = None
    irs_payroll_tax:         float | None = None
    texas_workforce:         float | None = None
    other_taxes:             float | None = None
    accounting_charges:      float | None = None
    other_expense_1:         float | None = None
    other_expense_2:         float | None = None
    other_expense_3:         float | None = None
    other_expense_4:         float | None = None
    other_expense_5:         float | None = None
    over_short:              float | None = None
    borrowed_money_return:   float | None = None
    profit_distributed:      float | None = None
    cash_carry_forward:      float | None = None
    notes:                   str = ""
