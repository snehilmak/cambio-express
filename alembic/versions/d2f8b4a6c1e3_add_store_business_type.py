"""add store.business_type

The pivot column: which kind of business a store is
(cstore / gas_station / grocery / msb_hybrid), driving module
defaults through the feature-flag bundle map. Every existing
store predates the pivot and is a money-service business, so the
backfill (via server_default) is "msb_hybrid" — nothing changes
for them.

Idempotent add via the shared ``_safe_add_column`` guard.

Revision ID: d2f8b4a6c1e3
Revises: c8d4e2f7a1b9
Create Date: 2026-08-22 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision: str = 'd2f8b4a6c1e3'
down_revision: Union[str, None] = 'c8d4e2f7a1b9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_column(table: str, column: str) -> bool:
    bind = op.get_bind()
    cols = {c["name"] for c in inspect(bind).get_columns(table)}
    return column in cols


def _safe_add_column(table: str, column_name: str, column) -> None:
    if _has_column(table, column_name):
        return
    try:
        op.add_column(table, column)
    except Exception as exc:
        msg = str(exc).lower()
        if "already exists" in msg or "duplicate column" in msg:
            return
        raise


def upgrade() -> None:
    _safe_add_column(
        "store", "business_type",
        sa.Column(
            "business_type", sa.String(20),
            nullable=False, server_default="msb_hybrid",
        ),
    )


def downgrade() -> None:
    with op.batch_alter_table("store") as batch:
        batch.drop_column("business_type")
