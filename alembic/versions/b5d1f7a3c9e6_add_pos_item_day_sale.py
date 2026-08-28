"""add pos_item_day_sale (G-2 — item movement)

Per-item net sales per business day, rebuilt from staged Gilbarco
journal originals at every day (re)commit.

Revision ID: b5d1f7a3c9e6
Revises: a3c9e5b7d1f4
Create Date: 2026-08-28 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision: str = 'b5d1f7a3c9e6'
down_revision: Union[str, None] = 'a3c9e5b7d1f4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(name: str) -> bool:
    bind = op.get_bind()
    return name in inspect(bind).get_table_names()


def upgrade() -> None:
    if not _has_table("pos_item_day_sale"):
        op.create_table(
            "pos_item_day_sale",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("store_id", sa.Integer(),
                      sa.ForeignKey("store.id"), nullable=False,
                      index=True),
            sa.Column("business_date", sa.Date(), nullable=False,
                      index=True),
            sa.Column("pos_code", sa.String(30), nullable=False),
            sa.Column("description", sa.String(160), nullable=False,
                      server_default=""),
            sa.Column("merchandise_code", sa.String(20), nullable=False,
                      server_default=""),
            sa.Column("quantity", sa.Float(), nullable=False,
                      server_default="0"),
            sa.Column("amount_cents", sa.BigInteger(), nullable=False,
                      server_default="0"),
            sa.UniqueConstraint(
                "store_id", "business_date", "pos_code",
            ),
        )


def downgrade() -> None:
    if _has_table("pos_item_day_sale"):
        op.drop_table("pos_item_day_sale")
