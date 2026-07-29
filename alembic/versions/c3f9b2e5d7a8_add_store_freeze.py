"""add store freeze (frozen_at + frozen_reason)

Superadmin store freeze (PR C). A platform operator can suspend a store
(abuse, dispute, non-payment follow-up) — distinct from trial-expired
and from retention-pause. The SPA gates a frozen store's users to a
"suspended, contact support" screen.

Schema additions
----------------
* ``store.frozen_at``     (DateTime, nullable) — set when suspended,
  cleared on unfreeze.
* ``store.frozen_reason`` (String(200), default "") — operator context
  for the audit log + superadmin UI.

Upgrade is idempotent — uses the ``_safe_add_column`` pattern shared by
the other recent revisions to survive Render's DuplicateColumn replay
quirk on Postgres.

Revision ID: c3f9b2e5d7a8
Revises: b1c2d3e4f5a6
Create Date: 2026-07-28 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision: str = 'c3f9b2e5d7a8'
down_revision: Union[str, None] = 'b1c2d3e4f5a6'
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
        "store", "frozen_at",
        sa.Column("frozen_at", sa.DateTime(), nullable=True),
    )
    _safe_add_column(
        "store", "frozen_reason",
        sa.Column(
            "frozen_reason", sa.String(length=200),
            nullable=True, server_default="",
        ),
    )


def downgrade() -> None:
    with op.batch_alter_table("store") as batch:
        batch.drop_column("frozen_reason")
        batch.drop_column("frozen_at")
