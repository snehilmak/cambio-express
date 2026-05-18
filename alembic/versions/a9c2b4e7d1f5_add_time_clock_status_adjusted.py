"""add time_clock_entry.status + adjusted

Inspiration-aligned upgrade to the v1 time-clock surface:

* ``status`` (``pending`` / ``approved`` / ``rejected``) —
  payroll workflow. New clock-in / clock-out entries default
  to ``pending``; the admin moves the row to ``approved``
  before it counts toward payroll. ``approved_hours`` +
  ``pending_hours`` are returned separately on the admin
  list endpoint so the SPA can split the headline KPIs.
* ``adjusted`` (Boolean) — explicit "this row was touched by
  an admin after the fact" flag. Set automatically whenever
  ``admin_update_entry`` lands a non-no-op patch. Surfaces as
  an "Adjusted: Yes/No" badge in the admin payroll view —
  same vocabulary as the inspiration screen.

Upgrade is idempotent — uses the same ``_has_column`` guard
as the other recent column-adding revisions so a DB whose
schema is ahead of the migration log (from ``create_all``
bootstrap) upgrades without ``DuplicateColumn``.

Revision ID: a9c2b4e7d1f5
Revises: f6e7a8b9c0d1
Create Date: 2026-05-18 06:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision: str = 'a9c2b4e7d1f5'
down_revision: Union[str, None] = 'f6e7a8b9c0d1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_column(table: str, column: str) -> bool:
    bind = op.get_bind()
    inspector = inspect(bind)
    cols = {c["name"] for c in inspector.get_columns(table)}
    return column in cols


def upgrade() -> None:
    if not _has_column("time_clock_entry", "status"):
        op.add_column(
            "time_clock_entry",
            sa.Column(
                "status", sa.String(20),
                nullable=True, server_default="pending",
            ),
        )
    if not _has_column("time_clock_entry", "adjusted"):
        op.add_column(
            "time_clock_entry",
            sa.Column(
                "adjusted", sa.Boolean(),
                nullable=True, server_default=sa.false(),
            ),
        )


def downgrade() -> None:
    op.drop_column("time_clock_entry", "adjusted")
    op.drop_column("time_clock_entry", "status")
