"""add time_clock_shift table

Shift scheduling primitive for the time-clock module.  Stores
"planned shifts": one row per roster member per planned shift,
with store-local Date + Time (so a schedule survives a timezone
change).  Decoupled from ``TimeClockEntry`` — punches stay the
source of truth for pay; shifts are the operator's plan.  v1
ships the data + admin CRUD; late-arrival / no-show derivation
against ``TimeClockEntry`` is a follow-up.

Schema additions
----------------
* ``time_clock_shift`` table
    * id (PK)
    * store_id (FK store.id)
    * store_employee_id (FK store_employee.id)
    * shift_date (Date, store-local)
    * start_time (Time, store-local)
    * end_time   (Time, store-local)
    * notes (String(500))
    * created_at (DateTime, UTC)
    * created_by_user_id (FK user.id)
* Composite index ``(store_id, shift_date)`` — date-window
  scans are the hot path on the admin schedule grid.

Upgrade is idempotent — uses ``CREATE TABLE IF NOT EXISTS`` via
the SQLAlchemy inspector check that the rest of the recent
revisions have been using to survive Render's replay quirks.

Revision ID: f1a8b3d92c47
Revises: e4a7c2f5d1b6
Create Date: 2026-05-19 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision: str = 'f1a8b3d92c47'
down_revision: Union[str, None] = 'e4a7c2f5d1b6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(name: str) -> bool:
    bind = op.get_bind()
    return name in inspect(bind).get_table_names()


def upgrade() -> None:
    if _has_table("time_clock_shift"):
        return
    op.create_table(
        "time_clock_shift",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "store_id", sa.Integer(),
            sa.ForeignKey("store.id"),
            nullable=False, index=True,
        ),
        sa.Column(
            "store_employee_id", sa.Integer(),
            sa.ForeignKey("store_employee.id"),
            nullable=False, index=True,
        ),
        sa.Column("shift_date", sa.Date(), nullable=False),
        sa.Column("start_time", sa.Time(), nullable=False),
        sa.Column("end_time",   sa.Time(), nullable=False),
        sa.Column("notes", sa.String(length=500), server_default=""),
        sa.Column(
            "created_at", sa.DateTime(),
            nullable=False, server_default=sa.func.now(),
        ),
        sa.Column(
            "created_by_user_id", sa.Integer(),
            sa.ForeignKey("user.id"), nullable=True,
        ),
    )
    op.create_index(
        "ix_time_clock_shift_store_date",
        "time_clock_shift",
        ["store_id", "shift_date"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_time_clock_shift_store_date",
        table_name="time_clock_shift",
    )
    op.drop_table("time_clock_shift")
