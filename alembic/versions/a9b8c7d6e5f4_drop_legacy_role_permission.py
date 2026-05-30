"""drop legacy role_permission and store_role_override

Revision ID: a9b8c7d6e5f4
Revises: 8676c548aa17
Create Date: 2026-05-28 03:30:00.000000

The custom RBAC tables (RolePermission, StoreRoleOverride) were
replaced with Casbin's casbin_rule table in PR #761. After a
stability period, the legacy tables are now dropped.

Data was migrated to Casbin on first boot via the
_migrate_legacy_to_casbin helper (since removed). Any rows that
weren't migrated before this revision applies will be lost — but
the Casbin enforcer's seed_defaults() ensures the system always
has a working baseline.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a9b8c7d6e5f4'
down_revision: Union[str, None] = '8676c548aa17'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_table('store_role_override')
    op.drop_table('role_permission')


def downgrade() -> None:
    op.create_table(
        'role_permission',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('role', sa.String(length=20), nullable=False),
        sa.Column('resource', sa.String(length=40), nullable=False),
        sa.Column('action', sa.String(length=20), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('role', 'resource', 'action',
                            name='uq_role_resource_action'),
    )
    op.create_index('ix_role_perm_role', 'role_permission', ['role'])
    op.create_table(
        'store_role_override',
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
    op.create_index('ix_store_role_override_store',
                    'store_role_override', ['store_id'])
    op.create_index('ix_store_role_override_store_role',
                    'store_role_override', ['store_id', 'role'])
