"""add store.timezone

Per-store IANA timezone for date / time rendering. The fallback
chain (per BACKLOG "Store timezone") is:

    user.timezone → store.timezone → browser default

When the user has a personal TZ set, use that. Otherwise fall
back to the store's TZ (where they work). Otherwise the
browser's default. Without this column the fallback was just
"UTC", which renders awkwardly for operators in CST / EST.

Defaults to empty string (== "unset, use the next layer"). The
admin settings page surfaces a dropdown with the same curated
choices the per-user profile already uses.

Upgrade is idempotent — uses an ``if not exists`` guard so a DB
bootstrapped via ``Base.metadata.create_all`` before this
revision shipped (which already has the column from the model
definition) doesn't crash the migration. The receipt-customization
migration hit this exact case on the first prod deploy.

Revision ID: 5f3a8b6e2c14
Revises: 2d8f1e6c4a09
Create Date: 2026-05-17 05:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision: str = '5f3a8b6e2c14'
down_revision: Union[str, None] = '2d8f1e6c4a09'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_column(table: str, column: str) -> bool:
    bind = op.get_bind()
    inspector = inspect(bind)
    cols = {c["name"] for c in inspector.get_columns(table)}
    return column in cols


def upgrade() -> None:
    if not _has_column("store", "timezone"):
        op.add_column(
            "store",
            sa.Column(
                "timezone", sa.String(60),
                nullable=True, server_default="",
            ),
        )


def downgrade() -> None:
    op.drop_column("store", "timezone")
