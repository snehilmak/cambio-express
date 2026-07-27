"""add announcement_store targeting table

Announcement targeting (PR B). A superadmin can now scope a broadcast
announcement to a subset of stores instead of every store. The
targeting lives in a join table:

* ``announcement_store`` — one row per (announcement, store) pair.

The ABSENCE of any row for an announcement means it's *global*
(visible to every store, emailed to every opted-in user) — the
back-compat default that every pre-targeting announcement keeps.
A non-empty set of rows scopes both the banner visibility
(``active_announcements``) and the broadcast fan-out
(``eligible_recipients``) to those stores.

Store deletion cascades through this table via the retention purge
registry (``STORE_OWNED_MODELS``); announcement deletion clears its
rows in the controller before the parent delete.

Idempotent create — mirrors the ``_has_table`` guard the other
recent revisions use so a DB whose schema is ahead of the migration
log (from an earlier ``create_all`` bootstrap) upgrades without a
DuplicateTable error on Postgres.

Revision ID: b1c2d3e4f5a6
Revises: a9b8c7d6e5f4
Create Date: 2026-07-27 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision: str = 'b1c2d3e4f5a6'
down_revision: Union[str, None] = 'a9b8c7d6e5f4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(table: str) -> bool:
    bind = op.get_bind()
    return table in inspect(bind).get_table_names()


def upgrade() -> None:
    if _has_table('announcement_store'):
        return
    op.create_table(
        'announcement_store',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('announcement_id', sa.Integer(), nullable=False),
        sa.Column('store_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['announcement_id'], ['announcement.id']),
        sa.ForeignKeyConstraint(['store_id'], ['store.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'announcement_id', 'store_id',
            name='uq_announcement_store',
        ),
    )
    op.create_index(
        'ix_announcement_store_store',
        'announcement_store', ['store_id'],
    )
    op.create_index(
        'ix_announcement_store_announcement',
        'announcement_store', ['announcement_id'],
    )


def downgrade() -> None:
    op.drop_index('ix_announcement_store_announcement',
                  table_name='announcement_store')
    op.drop_index('ix_announcement_store_store',
                  table_name='announcement_store')
    op.drop_table('announcement_store')
