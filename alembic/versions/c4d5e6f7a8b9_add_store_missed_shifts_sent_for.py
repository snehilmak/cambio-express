"""add store.missed_shifts_sent_for

Idempotency marker for the missed-shift digest cron — set by
``Notifications/Services/missed_shifts.run`` once a store's
digest is processed for a given date so a same-day re-run skips
that store.

Schema additions
----------------
* ``store.missed_shifts_sent_for`` (Date, nullable)

Upgrade is idempotent — uses the ``_safe_add_column`` pattern
shared by recent revisions to survive Render's DuplicateColumn
replay quirk on Postgres.

Revision ID: c4d5e6f7a8b9
Revises: b3c4d5e6f7a8
Create Date: 2026-05-19 20:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision: str = 'c4d5e6f7a8b9'
down_revision: Union[str, None] = 'b3c4d5e6f7a8'
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
        "store", "missed_shifts_sent_for",
        sa.Column(
            "missed_shifts_sent_for", sa.Date(), nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("store", "missed_shifts_sent_for")
