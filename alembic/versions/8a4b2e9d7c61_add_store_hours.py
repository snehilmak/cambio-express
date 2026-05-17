"""add store.store_hours

Per-store weekly business-hours schedule, persisted as a JSON
list of 7 entries (one per ISO weekday: 0=Monday … 6=Sunday).
Each entry: ``{"day": int, "open": "HH:MM", "close": "HH:MM",
"closed": bool}``.

Null / missing column means "not configured" — the admin
settings page renders a default Mon-Sat 09:00-18:00 / Sun closed
template the operator can save unchanged or edit.

This schema unblocks two follow-ups:
  - A "no transfers outside business hours" gating rule on the
    transfer form.
  - A peak-hour heatmap on the dashboard (overlay actual
    transfer-count traffic against open-hours bars).

Upgrade is idempotent — uses the same ``_has_column`` guard as
the timezone + receipt-customization revisions so a DB that
already has the column (because ``Base.metadata.create_all()``
materialized it from the model definition) doesn't crash.

Revision ID: 8a4b2e9d7c61
Revises: 5f3a8b6e2c14
Create Date: 2026-05-17 15:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision: str = '8a4b2e9d7c61'
down_revision: Union[str, None] = '5f3a8b6e2c14'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_column(table: str, column: str) -> bool:
    bind = op.get_bind()
    inspector = inspect(bind)
    cols = {c["name"] for c in inspector.get_columns(table)}
    return column in cols


def upgrade() -> None:
    if not _has_column("store", "store_hours"):
        op.add_column(
            "store",
            sa.Column("store_hours", sa.JSON(), nullable=True),
        )


def downgrade() -> None:
    op.drop_column("store", "store_hours")
