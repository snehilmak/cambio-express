"""add store.timeclock_late_minutes_threshold

Per-store lateness tolerance (in store-local minutes) for the
"Late by Xm" pill on the payroll history page.  Default 5
matches the comment in ``Store`` — small enough to flag real
lateness, big enough to absorb walking from the door to the
terminal.

Schema additions
----------------
* ``store.timeclock_late_minutes_threshold`` (Integer, default 5)

Upgrade is idempotent — uses the ``_safe_add_column`` pattern
shared by the other recent revisions to survive Render's
DuplicateColumn replay quirk on Postgres.

Revision ID: b3c4d5e6f7a8
Revises: a2b3c4d5e6f7
Create Date: 2026-05-19 18:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision: str = 'b3c4d5e6f7a8'
down_revision: Union[str, None] = 'a2b3c4d5e6f7'
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
        "store", "timeclock_late_minutes_threshold",
        sa.Column(
            "timeclock_late_minutes_threshold", sa.Integer(),
            nullable=True, server_default="5",
        ),
    )


def downgrade() -> None:
    op.drop_column("store", "timeclock_late_minutes_threshold")
