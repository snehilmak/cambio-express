"""add platform_setting table

Revision ID: 55952f4e1234
Revises: 44841e3e0123
Create Date: 2026-05-26

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '55952f4e1234'
down_revision: Union[str, None] = '44841e3e0123'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('platform_setting',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('key', sa.String(length=60), nullable=False),
        sa.Column('value', sa.Text(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('key'),
    )
    with op.batch_alter_table('platform_setting', schema=None) as batch_op:
        batch_op.create_index('ix_platform_setting_key', ['key'], unique=True)


def downgrade() -> None:
    with op.batch_alter_table('platform_setting', schema=None) as batch_op:
        batch_op.drop_index('ix_platform_setting_key')
    op.drop_table('platform_setting')
