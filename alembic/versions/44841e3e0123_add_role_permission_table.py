"""add role_permission table

Revision ID: 44841e3e0123
Revises: b2c3d4e5f6a7
Create Date: 2026-05-25 23:38:17.833670

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '44841e3e0123'
down_revision: Union[str, None] = 'b2c3d4e5f6a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('role_permission',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('role', sa.String(length=20), nullable=False),
        sa.Column('resource', sa.String(length=40), nullable=False),
        sa.Column('action', sa.String(length=20), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('role', 'resource', 'action',
                            name='uq_role_resource_action'),
    )
    with op.batch_alter_table('role_permission', schema=None) as batch_op:
        batch_op.create_index('ix_role_perm_role', ['role'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('role_permission', schema=None) as batch_op:
        batch_op.drop_index('ix_role_perm_role')
    op.drop_table('role_permission')
