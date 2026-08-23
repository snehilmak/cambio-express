"""add POS site-agent credentials + journal staging

P1-9 Phase B: pos_agent_credential (per-store agent API keys,
sha256-stored) and pos_journal_file (staged journal files pushed
by the site agent, gzipped raw XML, idempotent per filename).

Revision ID: a7b3e9f2c6d1
Revises: f3a9c1d5e8b2
Create Date: 2026-08-23 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision: str = 'a7b3e9f2c6d1'
down_revision: Union[str, None] = 'f3a9c1d5e8b2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(name: str) -> bool:
    bind = op.get_bind()
    return name in inspect(bind).get_table_names()


def upgrade() -> None:
    if not _has_table("pos_agent_credential"):
        op.create_table(
            "pos_agent_credential",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("store_id", sa.Integer(),
                      sa.ForeignKey("store.id"), nullable=False, index=True),
            sa.Column("key_hash", sa.String(64),
                      unique=True, nullable=False),
            sa.Column("label", sa.String(80),
                      nullable=False, server_default=""),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.Column("revoked_at", sa.DateTime(), nullable=True),
            sa.Column("last_used_at", sa.DateTime(), nullable=True),
        )
    if not _has_table("pos_journal_file"):
        op.create_table(
            "pos_journal_file",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("store_id", sa.Integer(),
                      sa.ForeignKey("store.id"), nullable=False, index=True),
            sa.Column("filename", sa.String(120), nullable=False),
            sa.Column("business_date", sa.Date(),
                      nullable=True, index=True),
            sa.Column("event_kind", sa.String(16),
                      nullable=False, server_default=""),
            sa.Column("parse_error", sa.String(255),
                      nullable=False, server_default=""),
            sa.Column("content_gz", sa.LargeBinary(), nullable=False),
            sa.Column("received_at", sa.DateTime(), nullable=True),
            sa.UniqueConstraint("store_id", "filename"),
        )


def downgrade() -> None:
    op.drop_table("pos_journal_file")
    op.drop_table("pos_agent_credential")
