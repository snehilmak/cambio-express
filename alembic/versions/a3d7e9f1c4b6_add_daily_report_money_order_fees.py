"""add daily_report.money_order_fees

New operator-editable receipt field on the daily book: the fee a
store charges to issue a money order (distinct from ``money_order``,
which is the face value moved). Groups with ``check_cashing_fees`` +
``return_check_hold_fees`` under the new "Fees" box in the editor.
Feeds ``DailyReport.total_receipts`` like the other fee columns.

Idempotent add (guards against Render replay / a column that already
exists on Postgres).

Revision ID: a3d7e9f1c4b6
Revises: f6c3a1b8d2e4
Create Date: 2026-08-08 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision: str = 'a3d7e9f1c4b6'
down_revision: Union[str, None] = 'f6c3a1b8d2e4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_column(table: str, column: str) -> bool:
    bind = op.get_bind()
    cols = {c["name"] for c in inspect(bind).get_columns(table)}
    return column in cols


def upgrade() -> None:
    if _has_column("daily_report", "money_order_fees"):
        return
    op.add_column(
        "daily_report",
        sa.Column("money_order_fees", sa.Float(), server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("daily_report", "money_order_fees")
