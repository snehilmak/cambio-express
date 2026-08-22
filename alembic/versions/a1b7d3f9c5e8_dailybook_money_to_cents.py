"""daily book: money Float dollars → BigInteger cents

P0-3 slice 3, the big one: all 28 DailyReport money columns plus
DailyDrop.amount, CheckDeposit.amount, DailyLineItem.amount and
the four MoneyTransferSummary columns become `*_cents` BigInteger.
Same in-place convert as e5b1c9f3a7d2: add, backfill
`ROUND(old * 100)`, drop old — reversible downgrade.

Revision ID: a1b7d3f9c5e8
Revises: f7c3d1a9b5e2
Create Date: 2026-08-22 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision: str = 'a1b7d3f9c5e8'
down_revision: Union[str, None] = 'f7c3d1a9b5e2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_DR_COLS = [
    "taxable_sales", "non_taxable", "sales_tax", "bill_payment_charge",
    "phone_recargas", "boost_mobile", "money_transfer", "money_order",
    "money_order_fees", "check_cashing_fees", "return_check_hold_fees",
    "return_check_paid_back", "forward_balance", "from_bank",
    "other_cash_in", "rebates_commissions", "cash_purchases",
    "cash_expense", "check_purchases", "check_expense",
    "outside_cash_drops", "cash_deposit", "checks_deposit",
    "safe_balance", "payroll_expense", "payroll_check",
    "other_cash_out", "over_short",
]

# (table, old_float_col, new_cents_col, not_null)
_CONVERSIONS = (
    [("daily_report", c, c + "_cents", False) for c in _DR_COLS]
    + [
        ("daily_drop",      "amount", "amount_cents", True),
        ("check_deposit",   "amount", "amount_cents", True),
        ("daily_line_item", "amount", "amount_cents", True),
        ("mt_summary", "amount",      "amount_cents",      False),
        ("mt_summary", "fees",        "fees_cents",        False),
        ("mt_summary", "commission",  "commission_cents",  False),
        ("mt_summary", "federal_tax", "federal_tax_cents", False),
    ]
)


def _columns(table: str) -> set[str]:
    bind = op.get_bind()
    return {c["name"] for c in inspect(bind).get_columns(table)}


def upgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"
    # Group by table so each table is rebuilt once (SQLite batch mode
    # recreates the table per batch context — fewer passes, same result).
    tables: dict[str, list[tuple[str, str, bool]]] = {}
    for table, old, new, not_null in _CONVERSIONS:
        tables.setdefault(table, []).append((old, new, not_null))

    for table, cols in tables.items():
        existing = _columns(table)
        for old, new, _ in cols:
            if new not in existing:
                op.add_column(
                    table, sa.Column(new, sa.BigInteger(), nullable=True),
                )
        for old, new, _ in cols:
            if old in existing:
                if is_postgres:
                    op.execute(
                        f"UPDATE {table} SET {new} = "
                        f"CAST(ROUND(CAST(COALESCE({old}, 0) AS numeric) * 100) AS bigint)"
                    )
                else:
                    op.execute(
                        f"UPDATE {table} SET {new} = "
                        f"CAST(ROUND(COALESCE({old}, 0) * 100) AS INTEGER)"
                    )
        with op.batch_alter_table(table) as batch:
            for old, new, not_null in cols:
                if old in existing:
                    batch.drop_column(old)
                if not_null:
                    batch.alter_column(
                        new, existing_type=sa.BigInteger(),
                        nullable=False, server_default="0",
                    )


def downgrade() -> None:
    tables: dict[str, list[tuple[str, str, bool]]] = {}
    for table, old, new, not_null in _CONVERSIONS:
        tables.setdefault(table, []).append((old, new, not_null))
    for table, cols in tables.items():
        for old, new, _ in cols:
            op.add_column(
                table, sa.Column("_tmp_" + old, sa.Float(), nullable=True),
            )
            op.execute(
                f"UPDATE {table} SET _tmp_{old} = COALESCE({new}, 0) / 100.0"
            )
        with op.batch_alter_table(table) as batch:
            for old, new, not_null in cols:
                batch.drop_column(new)
                batch.alter_column(
                    "_tmp_" + old, new_column_name=old,
                    existing_type=sa.Float(), nullable=not not_null,
                )
