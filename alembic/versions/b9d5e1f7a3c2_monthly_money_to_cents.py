"""monthly P&L: money Float dollars → BigInteger cents

P0-3 slice 4, the last table: all 38 MonthlyFinancial money
columns become `*_cents` BigInteger. Same in-place convert as
e5b1c9f3a7d2: add, backfill `ROUND(old * 100)`, drop old —
reversible downgrade.

Revision ID: b9d5e1f7a3c2
Revises: a1b7d3f9c5e8
Create Date: 2026-08-22 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision: str = 'b9d5e1f7a3c2'
down_revision: Union[str, None] = 'a1b7d3f9c5e8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_CONVERSIONS = [
    ("monthly_financial", "taxable_sales", "taxable_sales_cents", False),
    ("monthly_financial", "non_taxable", "non_taxable_cents", False),
    ("monthly_financial", "bill_payment_charge", "bill_payment_charge_cents", False),
    ("monthly_financial", "phone_recargas", "phone_recargas_cents", False),
    ("monthly_financial", "boost_mobile", "boost_mobile_cents", False),
    ("monthly_financial", "check_cashing_fees", "check_cashing_fees_cents", False),
    ("monthly_financial", "return_check_hold_fees", "return_check_hold_fees_cents", False),
    ("monthly_financial", "rebates_commissions", "rebates_commissions_cents", False),
    ("monthly_financial", "mt_commission_in_bank", "mt_commission_in_bank_cents", False),
    ("monthly_financial", "other_income_1", "other_income_1_cents", False),
    ("monthly_financial", "other_income_2", "other_income_2_cents", False),
    ("monthly_financial", "other_income_3", "other_income_3_cents", False),
    ("monthly_financial", "cash_purchases", "cash_purchases_cents", False),
    ("monthly_financial", "check_purchases", "check_purchases_cents", False),
    ("monthly_financial", "cash_expenses", "cash_expenses_cents", False),
    ("monthly_financial", "check_expenses", "check_expenses_cents", False),
    ("monthly_financial", "cash_payroll", "cash_payroll_cents", False),
    ("monthly_financial", "check_payroll", "check_payroll_cents", False),
    ("monthly_financial", "bank_charges_210", "bank_charges_210_cents", False),
    ("monthly_financial", "bank_charges_230", "bank_charges_230_cents", False),
    ("monthly_financial", "bank_charges_total", "bank_charges_total_cents", False),
    ("monthly_financial", "credit_card_fees", "credit_card_fees_cents", False),
    ("monthly_financial", "money_order_rent", "money_order_rent_cents", False),
    ("monthly_financial", "emaginenet_tech", "emaginenet_tech_cents", False),
    ("monthly_financial", "irs_payroll_tax", "irs_payroll_tax_cents", False),
    ("monthly_financial", "texas_workforce", "texas_workforce_cents", False),
    ("monthly_financial", "other_taxes", "other_taxes_cents", False),
    ("monthly_financial", "accounting_charges", "accounting_charges_cents", False),
    ("monthly_financial", "return_check_gl", "return_check_gl_cents", False),
    ("monthly_financial", "other_expense_1", "other_expense_1_cents", False),
    ("monthly_financial", "other_expense_2", "other_expense_2_cents", False),
    ("monthly_financial", "other_expense_3", "other_expense_3_cents", False),
    ("monthly_financial", "other_expense_4", "other_expense_4_cents", False),
    ("monthly_financial", "other_expense_5", "other_expense_5_cents", False),
    ("monthly_financial", "over_short", "over_short_cents", False),
    ("monthly_financial", "borrowed_money_return", "borrowed_money_return_cents", False),
    ("monthly_financial", "profit_distributed", "profit_distributed_cents", False),
    ("monthly_financial", "cash_carry_forward", "cash_carry_forward_cents", False),
]


def _columns(table: str) -> set[str]:
    bind = op.get_bind()
    return {c["name"] for c in inspect(bind).get_columns(table)}


def upgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"
    existing = _columns("monthly_financial")
    for _, old, new, _nn in _CONVERSIONS:
        if new not in existing:
            op.add_column(
                "monthly_financial",
                sa.Column(new, sa.BigInteger(), nullable=True),
            )
    for _, old, new, _nn in _CONVERSIONS:
        if old in existing:
            if is_postgres:
                op.execute(
                    f"UPDATE monthly_financial SET {new} = "
                    f"CAST(ROUND(CAST(COALESCE({old}, 0) AS numeric) * 100) AS bigint)"
                )
            else:
                op.execute(
                    f"UPDATE monthly_financial SET {new} = "
                    f"CAST(ROUND(COALESCE({old}, 0) * 100) AS INTEGER)"
                )
    with op.batch_alter_table("monthly_financial") as batch:
        for _, old, new, _nn in _CONVERSIONS:
            if old in existing:
                batch.drop_column(old)


def downgrade() -> None:
    for _, old, new, _nn in _CONVERSIONS:
        op.add_column(
            "monthly_financial",
            sa.Column("_tmp_" + old, sa.Float(), nullable=True),
        )
        op.execute(
            f"UPDATE monthly_financial SET _tmp_{old} = COALESCE({new}, 0) / 100.0"
        )
    with op.batch_alter_table("monthly_financial") as batch:
        for _, old, new, _nn in _CONVERSIONS:
            batch.drop_column(new)
            batch.alter_column(
                "_tmp_" + old, new_column_name=old,
                existing_type=sa.Float(), nullable=True,
            )
