"""price_book_item: item-editor parity fields (P2-5 phase 1)

Adds item_number, size, case_size, case_cost_cents, is_ebt.
Server-default backfills keep existing rows valid; the two case
fields are nullable (NULL = not tracked by the case).

Revision ID: f1b7d3a8c5e2
Revises: e8a4c6b2d9f3
Create Date: 2026-08-28 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision: str = 'f1b7d3a8c5e2'
down_revision: Union[str, None] = 'e8a4c6b2d9f3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLE = "price_book_item"

def _columns() -> "list[sa.Column]":
    # Fresh Column objects per call — a Column instance can only be
    # bound to one Table, so reuse across upgrade/downgrade breaks.
    return [
        sa.Column("item_number", sa.String(40), nullable=False,
                  server_default=""),
        sa.Column("size", sa.String(40), nullable=False,
                  server_default=""),
        sa.Column("case_size", sa.Integer(), nullable=True),
        sa.Column("case_cost_cents", sa.BigInteger(), nullable=True),
        sa.Column("is_ebt", sa.Boolean(), nullable=False,
                  server_default=sa.false()),
    ]


def _has_column(column: str) -> bool:
    bind = op.get_bind()
    return column in {c["name"] for c in inspect(bind).get_columns(_TABLE)}


def upgrade() -> None:
    for col in _columns():
        if not _has_column(col.name):
            op.add_column(_TABLE, col)


def downgrade() -> None:
    for col in reversed(_columns()):
        if _has_column(col.name):
            op.drop_column(_TABLE, col.name)
