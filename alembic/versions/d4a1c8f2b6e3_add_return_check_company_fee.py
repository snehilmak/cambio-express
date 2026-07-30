"""add return_check.company_name + return_check_fee

Two new fields on the bounced-check record:

* ``return_check.company_name``     (String(120), required at the API
  level) — the company on the check / associated business.
* ``return_check.return_check_fee`` (Float) — optional fee the store
  charges on a returned check. Reference only; does NOT feed the P&L.

Both carry a server_default so the add-column backfills existing rows
cleanly. Upgrade is idempotent via the shared ``_safe_add_column``
pattern (survives Render's DuplicateColumn replay on Postgres).

Revision ID: d4a1c8f2b6e3
Revises: c3f9b2e5d7a8
Create Date: 2026-07-29 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision: str = 'd4a1c8f2b6e3'
down_revision: Union[str, None] = 'c3f9b2e5d7a8'
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
        "return_check", "company_name",
        sa.Column(
            "company_name", sa.String(length=120),
            nullable=False, server_default="",
        ),
    )
    _safe_add_column(
        "return_check", "return_check_fee",
        sa.Column(
            "return_check_fee", sa.Float(),
            nullable=False, server_default="0",
        ),
    )


def downgrade() -> None:
    with op.batch_alter_table("return_check") as batch:
        batch.drop_column("return_check_fee")
        batch.drop_column("company_name")
