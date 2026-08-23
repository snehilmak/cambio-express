"""add Catalog: vendor + price_book_item

P2-1 (price book + vendors foundation, HANDOFF.md §2): two new
operator-owned catalogs. Items FK departments (DayClose) and
vendors; both links are nullable so an item can exist before the
operator has organized it.

Revision ID: b8d4f1a6c3e9
Revises: a7b3e9f2c6d1
Create Date: 2026-08-23 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision: str = 'b8d4f1a6c3e9'
down_revision: Union[str, None] = 'a7b3e9f2c6d1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(name: str) -> bool:
    bind = op.get_bind()
    return name in inspect(bind).get_table_names()


def upgrade() -> None:
    if not _has_table("vendor"):
        op.create_table(
            "vendor",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("store_id", sa.Integer(),
                      sa.ForeignKey("store.id"), nullable=False, index=True),
            sa.Column("name", sa.String(120), nullable=False),
            sa.Column("contact_name", sa.String(120), nullable=False,
                      server_default=""),
            sa.Column("phone", sa.String(30), nullable=False,
                      server_default=""),
            sa.Column("email", sa.String(200), nullable=False,
                      server_default=""),
            sa.Column("account_number", sa.String(60), nullable=False,
                      server_default=""),
            sa.Column("notes", sa.String(500), nullable=False,
                      server_default=""),
            sa.Column("is_active", sa.Boolean(), nullable=False,
                      server_default=sa.true()),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.UniqueConstraint("store_id", "name"),
        )
    if not _has_table("price_book_item"):
        op.create_table(
            "price_book_item",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("store_id", sa.Integer(),
                      sa.ForeignKey("store.id"), nullable=False, index=True),
            sa.Column("pos_code", sa.String(30), nullable=False),
            sa.Column("pos_code_format", sa.String(10), nullable=False,
                      server_default="upc"),
            sa.Column("name", sa.String(160), nullable=False),
            sa.Column("department_id", sa.Integer(),
                      sa.ForeignKey("department.id"), nullable=True,
                      index=True),
            sa.Column("vendor_id", sa.Integer(),
                      sa.ForeignKey("vendor.id"), nullable=True, index=True),
            sa.Column("price_cents", sa.BigInteger(), nullable=False,
                      server_default="0"),
            sa.Column("cost_cents", sa.BigInteger(), nullable=False,
                      server_default="0"),
            sa.Column("is_taxable", sa.Boolean(), nullable=False,
                      server_default=sa.true()),
            sa.Column("is_active", sa.Boolean(), nullable=False,
                      server_default=sa.true()),
            sa.Column("source", sa.String(20), nullable=False,
                      server_default="manual"),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
            sa.UniqueConstraint("store_id", "pos_code"),
        )


def downgrade() -> None:
    op.drop_table("price_book_item")
    op.drop_table("vendor")
