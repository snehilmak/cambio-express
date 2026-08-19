"""add store.companies_disabled

CSV subset of ``store.companies`` that's toggled OFF in the admin
Settings page. A disabled company stays on the store's roster (and
in historical MT-summary data) but is hidden from the daily book's
money-transfer breakdown and the transfer form. Empty string means
"nothing disabled" — every existing store keeps its current
behavior the moment this lands.

Idempotent add via the shared ``_safe_add_column`` guard (survives
Render's DuplicateColumn replay on Postgres).

Revision ID: c9f5a2e7b3d1
Revises: b8e2f4a1c9d7
Create Date: 2026-08-19 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision: str = 'c9f5a2e7b3d1'
down_revision: Union[str, None] = 'b8e2f4a1c9d7'
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
        "store", "companies_disabled",
        sa.Column(
            "companies_disabled", sa.String(500),
            nullable=False, server_default="",
        ),
    )


def downgrade() -> None:
    with op.batch_alter_table("store") as batch:
        batch.drop_column("companies_disabled")
