"""add store.sales_tax_rate

Per-store sales tax rate (decimal fraction, e.g. 0.0825 = 8.25%)
applied to a day's Taxable Sales in the daily book. Mirrors the
existing ``store.federal_tax_rate`` column. Defaults to 0.0 —
"no rate configured", which keeps the daily-book Sales Tax field
manually editable exactly as before this column existed.

Idempotent add via the shared ``_safe_add_column`` guard (survives
Render's DuplicateColumn replay on Postgres).

Revision ID: e5b2d9c4a7f1
Revises: d4a1c8f2b6e3
Create Date: 2026-07-31 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision: str = 'e5b2d9c4a7f1'
down_revision: Union[str, None] = 'd4a1c8f2b6e3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_column(table: str, column: str) -> bool:
    bind = op.get_bind()
    cols = {c["name"] for c in inspect(bind).get_columns(table)}
    return column in cols


def _safe_add_column(table: str, column_name: str, column) -> None:
    if _has_column(table, column_name):
        return
    try:
        op.add_column(table, column)
    except Exception as exc:
        msg = str(exc).lower()
        if "already exists" in msg or "duplicate column" in msg:
            return
        raise


def upgrade() -> None:
    _safe_add_column(
        "store", "sales_tax_rate",
        sa.Column(
            "sales_tax_rate", sa.Float(),
            nullable=False, server_default="0",
        ),
    )


def downgrade() -> None:
    with op.batch_alter_table("store") as batch:
        batch.drop_column("sales_tax_rate")
