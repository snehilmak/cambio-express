"""add POS import: merchandise mapping + register_close.source

P1-9 (Gilbarco Passport NAXML ingest): pos_merchandise_map holds
the operator's merchandise-code → department mapping, and
register_close gains a provenance column ("manual" default,
"gilbarco" for imported closes).

Revision ID: f3a9c1d5e8b2
Revises: e7d2c4b8a1f6
Create Date: 2026-08-23 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision: str = 'f3a9c1d5e8b2'
down_revision: Union[str, None] = 'e7d2c4b8a1f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(name: str) -> bool:
    bind = op.get_bind()
    return name in inspect(bind).get_table_names()


def _has_column(table: str, column: str) -> bool:
    bind = op.get_bind()
    return column in {
        c["name"] for c in inspect(bind).get_columns(table)
    }


def upgrade() -> None:
    if not _has_table("pos_merchandise_map"):
        op.create_table(
            "pos_merchandise_map",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("store_id", sa.Integer(),
                      sa.ForeignKey("store.id"), nullable=False, index=True),
            sa.Column("merchandise_code", sa.String(20), nullable=False),
            sa.Column("department_id", sa.Integer(),
                      sa.ForeignKey("department.id"), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.UniqueConstraint("store_id", "merchandise_code"),
        )
    if not _has_column("register_close", "source"):
        op.add_column(
            "register_close",
            sa.Column("source", sa.String(20),
                      nullable=False, server_default="manual"),
        )


def downgrade() -> None:
    op.drop_column("register_close", "source")
    op.drop_table("pos_merchandise_map")
