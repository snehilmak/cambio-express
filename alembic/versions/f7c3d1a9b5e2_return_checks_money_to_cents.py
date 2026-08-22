"""return checks: money Float dollars → BigInteger cents

P0-3 slice 2: `return_check.amount / return_check_fee` and
`return_check_payment.amount` become `*_cents` BigInteger columns.
Same in-place convert as e5b1c9f3a7d2 (Transfers/Batches): add,
backfill `ROUND(old * 100)`, drop old — reversible downgrade.

Revision ID: f7c3d1a9b5e2
Revises: e5b1c9f3a7d2
Create Date: 2026-08-22 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision: str = 'f7c3d1a9b5e2'
down_revision: Union[str, None] = 'e5b1c9f3a7d2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_CONVERSIONS = [
    ("return_check",         "amount",           "amount_cents",           True),
    ("return_check",         "return_check_fee", "return_check_fee_cents", True),
    ("return_check_payment", "amount",           "amount_cents",           True),
]


def _columns(table: str) -> set[str]:
    bind = op.get_bind()
    return {c["name"] for c in inspect(bind).get_columns(table)}


def upgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"
    for table, old, new, not_null in _CONVERSIONS:
        cols = _columns(table)
        if new in cols and old not in cols:
            continue  # already converted (idempotent re-run)
        if new not in cols:
            op.add_column(table, sa.Column(new, sa.BigInteger(), nullable=True))
        if old in cols:
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
                batch.drop_column(old)
        if not_null:
            with op.batch_alter_table(table) as batch:
                batch.alter_column(
                    new, existing_type=sa.BigInteger(),
                    nullable=False, server_default="0",
                )


def downgrade() -> None:
    for table, old, new, not_null in _CONVERSIONS:
        op.add_column(table, sa.Column("_tmp_" + old, sa.Float(), nullable=True))
        op.execute(f"UPDATE {table} SET _tmp_{old} = COALESCE({new}, 0) / 100.0")
        with op.batch_alter_table(table) as batch:
            batch.drop_column(new)
            batch.alter_column(
                "_tmp_" + old, new_column_name=old,
                existing_type=sa.Float(), nullable=not not_null,
            )
