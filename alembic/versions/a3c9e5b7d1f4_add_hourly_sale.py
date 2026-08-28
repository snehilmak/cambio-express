"""add hourly_sale (G-3 — dashboard hourly-sales chart)

Store-level net sales per clock hour of one business day, fed by
the Gilbarco journal ingestion (live at staging time, rebuilt at
commit time).

Revision ID: a3c9e5b7d1f4
Revises: f1b7d3a8c5e2
Create Date: 2026-08-28 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision: str = 'a3c9e5b7d1f4'
down_revision: Union[str, None] = 'f1b7d3a8c5e2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(name: str) -> bool:
    bind = op.get_bind()
    return name in inspect(bind).get_table_names()


def upgrade() -> None:
    if not _has_table("hourly_sale"):
        op.create_table(
            "hourly_sale",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("store_id", sa.Integer(),
                      sa.ForeignKey("store.id"), nullable=False,
                      index=True),
            sa.Column("report_date", sa.Date(), nullable=False,
                      index=True),
            sa.Column("hour", sa.Integer(), nullable=False),
            sa.Column("amount_cents", sa.BigInteger(), nullable=False,
                      server_default="0"),
            sa.Column("source", sa.String(20), nullable=False,
                      server_default="gilbarco"),
            sa.UniqueConstraint(
                "store_id", "report_date", "hour", "source",
            ),
        )


def downgrade() -> None:
    if _has_table("hourly_sale"):
        op.drop_table("hourly_sale")
