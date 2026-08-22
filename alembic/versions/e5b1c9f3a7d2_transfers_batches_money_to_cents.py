"""transfers + batches: money Float dollars → BigInteger cents

P0-3 (HANDOFF.md §2), first schema slice: `transfer.send_amount /
fee / federal_tax / commission` and `ach_batch.ach_amount` become
`*_cents` BigInteger columns holding exact integer cents.

In-place convert, NOT the rename-and-dual-write dance: each new
cents column is added, backfilled from the old Float in the same
revision (`ROUND(old * 100)` — no data loss), and the old column
dropped only after the backfill. The downgrade reverses it
exactly (cents / 100.0), so both directions preserve data — this
honors the intent of the CLAUDE.md no-drop-without-backfill rule
inside a single revision. Deploy note: migrations run on boot of
the same release that carries the code, so there is no old-code
window beyond the seconds of instance overlap; accepted pre-launch.

Revision ID: e5b1c9f3a7d2
Revises: d2f8b4a6c1e3
Create Date: 2026-08-22 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision: str = 'e5b1c9f3a7d2'
down_revision: Union[str, None] = 'd2f8b4a6c1e3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# (table, old_float_col, new_cents_col, not_null)
_CONVERSIONS = [
    ("transfer",  "send_amount", "send_amount_cents", True),
    ("transfer",  "fee",         "fee_cents",         False),
    ("transfer",  "federal_tax", "federal_tax_cents", False),
    ("transfer",  "commission",  "commission_cents",  False),
    ("ach_batch", "ach_amount",  "ach_amount_cents",  True),
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
            op.add_column(
                table,
                sa.Column(new, sa.BigInteger(), nullable=True),
            )
        # Backfill BEFORE dropping the source. ROUND() half-up
        # matches api.Core.Money.to_cents for the positive amounts
        # this schema stores.
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
        op.execute(
            f"UPDATE {table} SET _tmp_{old} = COALESCE({new}, 0) / 100.0"
        )
        with op.batch_alter_table(table) as batch:
            batch.drop_column(new)
            batch.alter_column(
                "_tmp_" + old, new_column_name=old,
                existing_type=sa.Float(), nullable=not not_null,
            )
