"""daily_line_item at_time nullable

Time field on daily line items is now optional — only money-
transfer drops need a time; all other line-item kinds (cash
purchases, expenses, deposits, etc.) track WHAT was logged,
not WHEN. Audit logs already capture the creation timestamp.

Revision ID: a1b2c3d4e5f6
Revises: f6e7a8b9c0d1
Create Date: 2026-05-25
"""
from alembic import op
import sqlalchemy as sa

revision = "a1b2c3d4e5f6"
down_revision = "c4d5e6f7a8b9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("daily_line_item") as batch_op:
        batch_op.alter_column(
            "at_time",
            existing_type=sa.Time(),
            nullable=True,
        )


def downgrade() -> None:
    with op.batch_alter_table("daily_line_item") as batch_op:
        batch_op.alter_column(
            "at_time",
            existing_type=sa.Time(),
            nullable=False,
        )
