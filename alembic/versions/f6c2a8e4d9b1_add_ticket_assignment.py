"""add support_ticket assignment columns

``assigned_to_user_id`` + ``assigned_to_name`` — which platform-
staff person claimed the ticket. Nullable (unclaimed is the
default state); the name is a display snapshot like
``submitted_by``.

Idempotent adds via the shared ``_safe_add_column`` guard.

Revision ID: f6c2a8e4d9b1
Revises: e7a3c9d5b2f4
Create Date: 2026-08-19 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision: str = 'f6c2a8e4d9b1'
down_revision: Union[str, None] = 'e7a3c9d5b2f4'
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
        "support_ticket", "assigned_to_user_id",
        sa.Column("assigned_to_user_id", sa.Integer(), nullable=True),
    )
    _safe_add_column(
        "support_ticket", "assigned_to_name",
        sa.Column("assigned_to_name", sa.String(120), nullable=True),
    )


def downgrade() -> None:
    with op.batch_alter_table("support_ticket") as batch:
        batch.drop_column("assigned_to_name")
        batch.drop_column("assigned_to_user_id")
