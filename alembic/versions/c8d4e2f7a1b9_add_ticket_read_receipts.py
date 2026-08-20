"""add support_ticket per-side read receipts

``user_last_seen_at`` + ``staff_last_seen_at`` — when each
conversation side (store users vs platform staff) last opened the
ticket thread. Drives the in-app unread badge. Nullable on purpose:
NULL means that side has never opened the thread since the feature
shipped, so every opposite-side message counts as unread — existing
staff replies light the badge up immediately at rollout instead of
being silently marked read.

Idempotent adds via the shared ``_safe_add_column`` guard.

Revision ID: c8d4e2f7a1b9
Revises: b3e7c1f9d5a2
Create Date: 2026-08-20 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision: str = 'c8d4e2f7a1b9'
down_revision: Union[str, None] = 'b3e7c1f9d5a2'
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
        "support_ticket", "user_last_seen_at",
        sa.Column("user_last_seen_at", sa.DateTime(), nullable=True),
    )
    _safe_add_column(
        "support_ticket", "staff_last_seen_at",
        sa.Column("staff_last_seen_at", sa.DateTime(), nullable=True),
    )


def downgrade() -> None:
    with op.batch_alter_table("support_ticket") as batch:
        batch.drop_column("staff_last_seen_at")
        batch.drop_column("user_last_seen_at")
