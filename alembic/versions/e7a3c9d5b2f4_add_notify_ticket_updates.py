"""add user.notify_ticket_updates(+_push) preference columns

Per-user opt-out toggles for support-ticket update notifications
(staff replied / status changed on a ticket the user created).
Default True on both channels — mirrors the trial-reminder /
daily-summary opt-out pattern.

Idempotent adds via the shared ``_safe_add_column`` guard.

Revision ID: e7a3c9d5b2f4
Revises: d2e8b4f6a1c3
Create Date: 2026-08-19 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision: str = 'e7a3c9d5b2f4'
down_revision: Union[str, None] = 'd2e8b4f6a1c3'
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
        "user", "notify_ticket_updates",
        sa.Column(
            "notify_ticket_updates", sa.Boolean(),
            nullable=False, server_default=sa.true(),
        ),
    )
    _safe_add_column(
        "user", "notify_ticket_updates_push",
        sa.Column(
            "notify_ticket_updates_push", sa.Boolean(),
            nullable=False, server_default=sa.true(),
        ),
    )


def downgrade() -> None:
    with op.batch_alter_table("user") as batch:
        batch.drop_column("notify_ticket_updates_push")
        batch.drop_column("notify_ticket_updates")
