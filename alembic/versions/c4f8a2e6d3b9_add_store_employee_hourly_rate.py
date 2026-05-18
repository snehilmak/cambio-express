"""add store_employee.hourly_rate

Adds the per-cashier pay rate used by the paystub computation.
The admin sets it from Settings → Team alongside the cashier's
display name; the time-clock paystub view multiplies
``approved_hours × hourly_rate`` to print the gross pay for a
date range.

Default ``0.0`` means "rate not configured" — the paystub view
shows a dash in the gross-pay column until the admin sets a
real number. Negative rates are rejected by the admin endpoint.

Upgrade is idempotent — uses the ``_safe_add_column`` pattern
from the recent revisions so a DB whose schema is ahead of the
alembic_version row doesn't crash on ``DuplicateColumn``.

Revision ID: c4f8a2e6d3b9
Revises: b3d5e7f9a2c1
Create Date: 2026-05-18 08:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision: str = 'c4f8a2e6d3b9'
down_revision: Union[str, None] = 'b3d5e7f9a2c1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_column(table: str, column: str) -> bool:
    bind = op.get_bind()
    cols = {c["name"] for c in inspect(bind).get_columns(table)}
    return column in cols


def _safe_add_column(table: str, column_name: str, column) -> None:
    """Idempotent add_column — see the matching helper in
    revision ``a9c2b4e7d1f5`` for the rationale."""
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
        "store_employee", "hourly_rate",
        sa.Column(
            "hourly_rate", sa.Float(),
            nullable=True, server_default="0.0",
        ),
    )


def downgrade() -> None:
    op.drop_column("store_employee", "hourly_rate")
