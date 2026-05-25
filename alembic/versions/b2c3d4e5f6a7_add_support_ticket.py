"""Add support_ticket table

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-05-25
"""
from alembic import op
import sqlalchemy as sa

revision = "b2c3d4e5f6a7"
down_revision = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "support_ticket",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("store_id", sa.Integer, sa.ForeignKey("store.id"), nullable=False, index=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("user.id"), nullable=False, index=True),
        sa.Column("submitted_by", sa.String(120), nullable=False),
        sa.Column("category", sa.String(30), nullable=False, server_default="question"),
        sa.Column("priority", sa.String(10), nullable=True),
        sa.Column("subject", sa.String(200), nullable=False),
        sa.Column("body", sa.Text, nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="open"),
        sa.Column("admin_reply", sa.Text, nullable=True),
        sa.Column("replied_at", sa.DateTime, nullable=True),
        sa.Column("replied_by", sa.String(120), nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("closed_at", sa.DateTime, nullable=True),
    )


def downgrade() -> None:
    op.drop_table("support_ticket")
