"""add store legal info + owner notification columns

Revision ID: 8676c548aa17
Revises: 66a63b5e2345
Create Date: 2026-05-27 12:21:41.318059

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8676c548aa17'
down_revision: Union[str, None] = '66a63b5e2345'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('store', schema=None) as batch_op:
        batch_op.add_column(sa.Column('legal_name', sa.String(length=200), nullable=True))
        batch_op.add_column(sa.Column('ein', sa.String(length=20), nullable=True))
        batch_op.add_column(sa.Column('business_address', sa.String(length=500), nullable=True))

    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.add_column(sa.Column('notify_high_variance', sa.Boolean(), nullable=True))
        batch_op.add_column(sa.Column('notify_high_variance_push', sa.Boolean(), nullable=True))
        batch_op.add_column(sa.Column('notify_store_offline', sa.Boolean(), nullable=True))
        batch_op.add_column(sa.Column('notify_store_offline_push', sa.Boolean(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.drop_column('notify_store_offline_push')
        batch_op.drop_column('notify_store_offline')
        batch_op.drop_column('notify_high_variance_push')
        batch_op.drop_column('notify_high_variance')

    with op.batch_alter_table('store', schema=None) as batch_op:
        batch_op.drop_column('business_address')
        batch_op.drop_column('ein')
        batch_op.drop_column('legal_name')
