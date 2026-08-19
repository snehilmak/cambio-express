"""add support_message thread + backfill legacy admin replies

The ticket "reply" used to be a single overwritable
``support_ticket.admin_reply`` column. This adds the proper
conversation-thread table and backfills one staff message per
ticket that had a non-empty legacy reply (author = ``replied_by``
snapshot, timestamp = ``replied_at``), so existing conversations
show up in the new thread UI. The legacy columns stay (dual-written
with the latest staff message for back-compat) — no column drops.

Idempotent: table create is guarded, and the backfill only runs
when the table was just created (re-running on an already-migrated
DB inserts nothing).

Revision ID: d2e8b4f6a1c3
Revises: c9f5a2e7b3d1
Create Date: 2026-08-19 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision: str = 'd2e8b4f6a1c3'
down_revision: Union[str, None] = 'c9f5a2e7b3d1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(name: str) -> bool:
    bind = op.get_bind()
    return name in inspect(bind).get_table_names()


def upgrade() -> None:
    if _has_table("support_message"):
        return
    op.create_table(
        "support_message",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "ticket_id", sa.Integer(),
            sa.ForeignKey("support_ticket.id"), nullable=False,
        ),
        sa.Column(
            "store_id", sa.Integer(),
            sa.ForeignKey("store.id"), nullable=False,
        ),
        sa.Column(
            "author_user_id", sa.Integer(),
            sa.ForeignKey("user.id"), nullable=True,
        ),
        sa.Column(
            "author_name", sa.String(120),
            nullable=False, server_default="",
        ),
        sa.Column(
            "author_kind", sa.String(10),
            nullable=False, server_default="user",
        ),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index(
        "ix_support_message_ticket_id", "support_message", ["ticket_id"],
    )
    op.create_index(
        "ix_support_message_store_id", "support_message", ["store_id"],
    )
    # Backfill: one staff message per ticket with a legacy reply.
    # replied_at can be NULL on very old rows — fall back to the
    # ticket's updated_at so created_at stays NOT NULL.
    op.execute(sa.text(
        """
        INSERT INTO support_message
            (ticket_id, store_id, author_user_id, author_name,
             author_kind, body, created_at)
        SELECT t.id, t.store_id, NULL,
               COALESCE(t.replied_by, ''), 'staff', t.admin_reply,
               COALESCE(t.replied_at, t.updated_at)
        FROM support_ticket t
        WHERE t.admin_reply IS NOT NULL AND t.admin_reply != ''
        """
    ))


def downgrade() -> None:
    op.drop_index("ix_support_message_ticket_id", "support_message")
    op.drop_index("ix_support_message_store_id", "support_message")
    op.drop_table("support_message")
