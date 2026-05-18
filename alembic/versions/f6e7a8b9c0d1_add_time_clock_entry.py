"""add time_clock_entry table

Time-clock v1 — employees clock in / clock out at their store.
One row per shift. Per-StoreEmployee, NOT per-User, because all
in-store cashiers typically share one ``employee`` User login;
the human is identified by the roster row they pick at the
punch page.

Columns:

* ``store_id``           — store the shift happened at (tenancy
                           anchor, included on every query).
* ``store_employee_id``  — the human (FK ``store_employee.id``)
                           the entry is attributed to. Picked
                           from the roster on the punch page.
* ``clock_in_user_id``   — login that initiated the punch
                           (audit hint, may be the shared employee
                           User or a personal admin login).
* ``clock_out_user_id``  — login that closed the shift (may
                           differ from clock_in_user_id if the
                           cashier ends their shift on a
                           different device / session).
* ``clock_in_at`` /
  ``clock_out_at``       — UTC timestamps. SPA formats per
                           ``Store.timezone``.
* ``hours_worked``       — denormalized for cheap payroll
                           rollups. Computed at clock-out.
* ``notes``              — free-form 500-char (operator
                           "covered for Maria 5 min late" etc.).

The composite index on ``(store_employee_id, clock_out_at)``
makes the "is this employee currently clocked in?" lookup
(open entries have ``clock_out_at IS NULL``) one index probe.

Revision ID: f6e7a8b9c0d1
Revises: e5b4c3d2f1a9
Create Date: 2026-05-18 02:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision: str = 'f6e7a8b9c0d1'
down_revision: Union[str, None] = 'e5b4c3d2f1a9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_exists(name: str) -> bool:
    bind = op.get_bind()
    return name in set(inspect(bind).get_table_names())


def _index_names(table: str) -> set[str]:
    bind = op.get_bind()
    return {idx["name"] for idx in inspect(bind).get_indexes(table)}


def upgrade() -> None:
    if not _table_exists("time_clock_entry"):
        op.create_table(
            "time_clock_entry",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column(
                "store_id", sa.Integer,
                sa.ForeignKey("store.id"), nullable=False, index=True,
            ),
            sa.Column(
                "store_employee_id", sa.Integer,
                sa.ForeignKey("store_employee.id"),
                nullable=False, index=True,
            ),
            sa.Column(
                "clock_in_user_id", sa.Integer,
                sa.ForeignKey("user.id"), nullable=True,
            ),
            sa.Column(
                "clock_out_user_id", sa.Integer,
                sa.ForeignKey("user.id"), nullable=True,
            ),
            sa.Column("clock_in_at", sa.DateTime, nullable=False),
            sa.Column("clock_out_at", sa.DateTime, nullable=True),
            sa.Column("hours_worked", sa.Float, nullable=True),
            sa.Column("notes", sa.String(500), nullable=True, server_default=""),
        )
    if _table_exists("time_clock_entry"):
        existing_idx = _index_names("time_clock_entry")
        if "ix_time_clock_employee_open" not in existing_idx:
            op.create_index(
                "ix_time_clock_employee_open",
                "time_clock_entry",
                ["store_employee_id", "clock_out_at"],
            )


def downgrade() -> None:
    op.drop_index(
        "ix_time_clock_employee_open", table_name="time_clock_entry",
    )
    op.drop_table("time_clock_entry")
