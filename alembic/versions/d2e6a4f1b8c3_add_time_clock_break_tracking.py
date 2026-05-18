"""add time_clock_entry break tracking

Adds two columns so cashiers can pause / resume a shift for
meal + short breaks without closing the entry. ``hours_worked``
becomes ``elapsed - break_minutes`` at clock-out (was just
``elapsed``).

Columns:

* ``break_started_at`` (DateTime, nullable) — set when the
  cashier taps "Start break"; cleared on "End break". A
  non-null value means the entry is currently paused.
* ``break_minutes`` (Float, default 0.0) — running total of
  break time accumulated across multiple pause/resume cycles
  within a single shift.

Upgrade is idempotent — uses the same ``_safe_add_column``
pattern as the recent revisions.

Revision ID: d2e6a4f1b8c3
Revises: c4f8a2e6d3b9
Create Date: 2026-05-18 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision: str = 'd2e6a4f1b8c3'
down_revision: Union[str, None] = 'c4f8a2e6d3b9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_column(table: str, column: str) -> bool:
    bind = op.get_bind()
    cols = {c["name"] for c in inspect(bind).get_columns(table)}
    return column in cols


def _safe_add_column(table: str, column_name: str, column) -> None:
    if _has_column(table, column_name):
        return
    try:
        op.add_column(table, column)
    except Exception as exc:
        msg = str(exc).lower()
        if "already exists" in msg or "duplicate column" in msg:
            return
        raise


def upgrade() -> None:
    _safe_add_column(
        "time_clock_entry", "break_started_at",
        sa.Column("break_started_at", sa.DateTime(), nullable=True),
    )
    _safe_add_column(
        "time_clock_entry", "break_minutes",
        sa.Column(
            "break_minutes", sa.Float(),
            nullable=True, server_default="0.0",
        ),
    )


def downgrade() -> None:
    op.drop_column("time_clock_entry", "break_minutes")
    op.drop_column("time_clock_entry", "break_started_at")
