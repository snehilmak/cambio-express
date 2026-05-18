"""add store.enforce_business_hours

Per-store opt-in toggle that gates the transfer create / update
endpoints. When True, transfer saves outside the configured
``store_hours`` window are refused with 422. Default False so
existing stores aren't disrupted — the operator turns it on
explicitly from the Settings page.

The "soft warning" indicator on the New Transfer form fires
regardless of this toggle (see PR for ``getOpenStatus``);
this column is what turns the warning into a hard gate.

Upgrade is idempotent — reuses the ``_has_column`` guard from
the timezone / store-hours migrations so a DB whose schema is
ahead of the migration log (from ``Base.metadata.create_all()``
bootstrap) upgrades without ``DuplicateColumn``.

Revision ID: e5b4c3d2f1a9
Revises: 8a4b2e9d7c61
Create Date: 2026-05-17 23:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision: str = 'e5b4c3d2f1a9'
down_revision: Union[str, None] = '8a4b2e9d7c61'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_column(table: str, column: str) -> bool:
    bind = op.get_bind()
    inspector = inspect(bind)
    cols = {c["name"] for c in inspector.get_columns(table)}
    return column in cols


def upgrade() -> None:
    if not _has_column("store", "enforce_business_hours"):
        op.add_column(
            "store",
            sa.Column(
                "enforce_business_hours", sa.Boolean(),
                nullable=True, server_default=sa.false(),
            ),
        )


def downgrade() -> None:
    op.drop_column("store", "enforce_business_hours")
