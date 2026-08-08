"""add owner_audit_log

Append-only audit table for multi-store OWNER actions that aren't
scoped to a single store (connect-code mint / revoke). Owners span
many stores, so these don't fit the store-scoped operator_audit_log;
and the actor is an owner, not a superadmin, so superadmin_audit_log
would misattribute them. See api/Modules/Audit/Models.OwnerAuditLog.

Idempotent create (guards against Render replay / a table that
already exists on Postgres).

Revision ID: f6c3a1b8d2e4
Revises: e5b2d9c4a7f1
Create Date: 2026-08-07 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision: str = 'f6c3a1b8d2e4'
down_revision: Union[str, None] = 'e5b2d9c4a7f1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(table: str) -> bool:
    bind = op.get_bind()
    return inspect(bind).has_table(table)


def upgrade() -> None:
    if _has_table("owner_audit_log"):
        return
    op.create_table(
        "owner_audit_log",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "owner_id", sa.Integer(),
            sa.ForeignKey("user.id"), nullable=False, index=True,
        ),
        sa.Column("owner_name", sa.String(length=120), server_default=""),
        sa.Column("action", sa.String(length=40), nullable=False),
        sa.Column("target_type", sa.String(length=30), server_default=""),
        sa.Column("target_id", sa.String(length=60), server_default=""),
        sa.Column("details", sa.Text(), server_default=""),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("owner_audit_log")
