"""add store legal-info columns

Per-store business-legal block: legal name (as registered with
the state), EIN / tax ID (federal), and legal address. These
land on every printed receipt under the store wordmark when set
and surface in admin Settings as a separate "Business legal
info" section. Future tax-pack / 1099 exports will read these
without needing the operator to fill them in again.

* ``legal_name`` — separate from ``Store.name`` so the public-
  facing wordmark can stay short (e.g. "Maxi NYC") while the
  receipt + tax pack carry the full legal entity name (e.g.
  "Maxi Remittance Services LLC").
* ``ein`` — federal tax ID (XX-XXXXXXX). Distinct from
  ``receipt_tax_id`` which is freeform receipt-display copy —
  EIN is canonical legal data the operator only types once.
* ``legal_address`` — registered business address. Falls back
  to ``Store.address`` on the receipt when empty so an operator
  who hasn't filled it in still gets a non-blank line.

Upgrade is idempotent — the same ``_existing_columns`` /
``_add_column_if_missing`` pattern as the receipt-customization
+ timezone + store-hours migrations so a DB whose schema is
ahead of the migration log doesn't crash.

Revision ID: c4d6f8a1b2e3
Revises: 8a4b2e9d7c61
Create Date: 2026-05-17 17:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision: str = 'c4d6f8a1b2e3'
down_revision: Union[str, None] = '8a4b2e9d7c61'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _existing_columns(table: str) -> set[str]:
    bind = op.get_bind()
    inspector = inspect(bind)
    return {col["name"] for col in inspector.get_columns(table)}


def _add_column_if_missing(
    table: str,
    column: sa.Column,
    existing: set[str],
) -> None:
    if column.name in existing:
        return
    op.add_column(table, column)
    existing.add(column.name)


def upgrade() -> None:
    existing = _existing_columns("store")
    _add_column_if_missing(
        "store",
        sa.Column("legal_name", sa.String(200),
                  nullable=True, server_default=""),
        existing,
    )
    _add_column_if_missing(
        "store",
        sa.Column("ein", sa.String(20),
                  nullable=True, server_default=""),
        existing,
    )
    _add_column_if_missing(
        "store",
        sa.Column("legal_address", sa.String(500),
                  nullable=True, server_default=""),
        existing,
    )


def downgrade() -> None:
    op.drop_column("store", "legal_address")
    op.drop_column("store", "ein")
    op.drop_column("store", "legal_name")
