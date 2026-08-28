"""add user.module_access

Per-user module access grants (U-3): NULL = every module the
store has enabled; a CSV subset restricts which optional modules
show in this user's nav/session. UX gating only — routes stay
permission-gated via Casbin. Owners and superadmin are never
restricted.

Revision ID: e8a4c6b2d9f3
Revises: d7f2b9c4e1a8
Create Date: 2026-08-27 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision: str = 'e8a4c6b2d9f3'
down_revision: Union[str, None] = 'd7f2b9c4e1a8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_column(table: str, column: str) -> bool:
    bind = op.get_bind()
    return column in {c["name"] for c in inspect(bind).get_columns(table)}


def upgrade() -> None:
    if not _has_column("user", "module_access"):
        op.add_column(
            "user", sa.Column("module_access", sa.String(300), nullable=True)
        )


def downgrade() -> None:
    if _has_column("user", "module_access"):
        op.drop_column("user", "module_access")
