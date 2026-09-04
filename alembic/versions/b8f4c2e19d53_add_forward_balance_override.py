"""add daily_report.forward_balance_override_cents

Operator override of the auto-carried opening balance (M-1).

Columns spelled out literally, never derived from the model — a
migration is immutable history (CLAUDE.md "Migrations").

Revision ID: b8f4c2e19d53
Revises: a3d7e91c4b26
Create Date: 2026-09-01
"""
from alembic import op
import sqlalchemy as sa


revision = "b8f4c2e19d53"
down_revision = "a3d7e91c4b26"
branch_labels = None
depends_on = None


def _has_column(table: str, column: str) -> bool:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if not insp.has_table(table):
        return False
    return column in {c["name"] for c in insp.get_columns(table)}


def upgrade() -> None:
    # NULL-able with no default and no backfill: NULL means "follow
    # the carry", which is exactly what every existing row does
    # today. Nothing changes for anyone until an operator overrides
    # a specific day.
    if not _has_column("daily_report", "forward_balance_override_cents"):
        op.add_column(
            "daily_report",
            sa.Column(
                "forward_balance_override_cents",
                sa.BigInteger(), nullable=True,
            ),
        )


def downgrade() -> None:
    # Dropping this DISCARDS every operator override and the affected
    # days silently revert to the carried value. The stored
    # forward_balance_cents keeps the pinned number until that day is
    # next saved, so the visible figures do not jump on downgrade.
    if _has_column("daily_report", "forward_balance_override_cents"):
        with op.batch_alter_table("daily_report") as batch:
            batch.drop_column("forward_balance_override_cents")
