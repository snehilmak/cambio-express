"""add day-close tables (P1-7 — generalized retail day-close)

Three tables: department (per-store department catalog — the
future price book hangs off the same rows), register_close (one
register/shift Z-report per day), and department_sale (one
department's sales line on one close; store_id denormalized for
the retention purge). Money is integer cents from day one — no
Float columns (P0-3 convention).

Revision ID: e7d2c4b8a1f6
Revises: c4e8a2d6f1b3
Create Date: 2026-08-23 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision: str = 'e7d2c4b8a1f6'
down_revision: Union[str, None] = 'c4e8a2d6f1b3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(name: str) -> bool:
    bind = op.get_bind()
    return name in inspect(bind).get_table_names()


def upgrade() -> None:
    if not _has_table("department"):
        op.create_table(
            "department",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("store_id", sa.Integer(),
                      sa.ForeignKey("store.id"), nullable=False, index=True),
            sa.Column("name", sa.String(80), nullable=False),
            sa.Column("sort_order", sa.Integer(),
                      nullable=False, server_default="0"),
            sa.Column("is_active", sa.Boolean(),
                      nullable=False, server_default=sa.true()),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.UniqueConstraint("store_id", "name"),
        )
    if not _has_table("register_close"):
        op.create_table(
            "register_close",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("store_id", sa.Integer(),
                      sa.ForeignKey("store.id"), nullable=False, index=True),
            sa.Column("report_date", sa.Date(), nullable=False),
            sa.Column("register_label", sa.String(40), nullable=False),
            sa.Column("shift_label", sa.String(40),
                      nullable=False, server_default=""),
            sa.Column("gross_sales_cents", sa.BigInteger(),
                      nullable=False, server_default="0"),
            sa.Column("sales_tax_cents", sa.BigInteger(),
                      nullable=False, server_default="0"),
            sa.Column("cash_total_cents", sa.BigInteger(),
                      nullable=False, server_default="0"),
            sa.Column("card_total_cents", sa.BigInteger(),
                      nullable=False, server_default="0"),
            sa.Column("other_total_cents", sa.BigInteger(),
                      nullable=False, server_default="0"),
            sa.Column("cash_counted_cents", sa.BigInteger(), nullable=True),
            sa.Column("notes", sa.String(500),
                      nullable=False, server_default=""),
            sa.Column("created_by", sa.Integer(),
                      sa.ForeignKey("user.id"), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.UniqueConstraint(
                "store_id", "report_date", "register_label", "shift_label",
            ),
        )
    if not _has_table("department_sale"):
        op.create_table(
            "department_sale",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("store_id", sa.Integer(),
                      sa.ForeignKey("store.id"), nullable=False, index=True),
            sa.Column("register_close_id", sa.Integer(),
                      sa.ForeignKey("register_close.id"),
                      nullable=False, index=True),
            sa.Column("department_id", sa.Integer(),
                      sa.ForeignKey("department.id"),
                      nullable=False, index=True),
            sa.Column("amount_cents", sa.BigInteger(),
                      nullable=False, server_default="0"),
            sa.UniqueConstraint("register_close_id", "department_id"),
        )


def downgrade() -> None:
    op.drop_table("department_sale")
    op.drop_table("register_close")
    op.drop_table("department")
