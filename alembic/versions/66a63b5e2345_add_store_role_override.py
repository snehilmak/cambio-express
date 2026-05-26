"""add store_role_override table

Revision ID: 66a63b5e2345
Revises: 55952f4e1234
Create Date: 2026-05-27

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '66a63b5e2345'
down_revision: Union[str, None] = '55952f4e1234'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('store_role_override',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('store_id', sa.Integer(), nullable=False),
        sa.Column('role', sa.String(length=20), nullable=False),
        sa.Column('resource', sa.String(length=40), nullable=False),
        sa.Column('action', sa.String(length=20), nullable=False),
        sa.ForeignKeyConstraint(['store_id'], ['store.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('store_id', 'role', 'resource', 'action',
                            name='uq_store_role_resource_action'),
    )
    with op.batch_alter_table('store_role_override', schema=None) as batch_op:
        batch_op.create_index('ix_store_role_override_store', ['store_id'])
        batch_op.create_index('ix_store_role_override_store_role',
                              ['store_id', 'role'])


def downgrade() -> None:
    with op.batch_alter_table('store_role_override', schema=None) as batch_op:
        batch_op.drop_index('ix_store_role_override_store_role')
        batch_op.drop_index('ix_store_role_override_store')
    op.drop_table('store_role_override')
