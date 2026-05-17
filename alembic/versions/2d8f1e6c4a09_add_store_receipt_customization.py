"""add store.receipt_* customization fields

Three new columns to support per-store branded transfer receipts:

  * ``receipt_logo_url``  — public URL for the store's logo image.
                            Empty means "no logo" — the receipt
                            falls back to the store name as a
                            wordmark. Cap at 500 chars (URLs can
                            be long; 500 covers Cloudinary /
                            Imgix / signed-S3 typical lengths).
  * ``receipt_footer``    — free-form text printed at the bottom
                            of every receipt. Refund policy,
                            compliance disclaimers, custom thank-
                            you. Cap at 500 chars so a printable
                            receipt stays on one page.
  * ``receipt_tax_id``    — store's federal tax ID / EIN / VAT
                            number to print near the header. Some
                            jurisdictions require it; others
                            don't. 40-char cap accommodates the
                            longest international format.

All three default to empty string. Stores that don't customize
fall back to the default receipt layout.

The upgrade is idempotent — uses ``_add_column_if_missing`` so
a DB that already has the column (because an earlier deploy
applied an out-of-band ALTER TABLE, or a long-ago
``db.create_all()`` materialized the schema before Alembic was
in charge) doesn't crash the migration. The first prod deploy
of this revision hit ``DuplicateColumn`` on ``receipt_logo_url``
because the production DB had been bootstrapped via
``Base.metadata.create_all()`` before this migration shipped,
which materialized the column from the model definition before
Alembic could.

Revision ID: 2d8f1e6c4a09
Revises: 9c5e21a4f8b3
Create Date: 2026-05-17 05:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision: str = '2d8f1e6c4a09'
down_revision: Union[str, None] = '9c5e21a4f8b3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _existing_columns(table: str) -> set[str]:
    """Inspect the live DB and return the column names already on
    ``table``. Caller uses this to skip ``add_column`` calls that
    would otherwise raise ``DuplicateColumn`` on a DB whose
    schema is ahead of the migration log."""
    bind = op.get_bind()
    inspector = inspect(bind)
    return {col["name"] for col in inspector.get_columns(table)}


def _add_column_if_missing(
    table: str,
    column: sa.Column,
    existing: set[str],
) -> None:
    """Skip ``add_column`` when the column already exists. Tracks
    the result in ``existing`` so subsequent calls in the same
    upgrade see the up-to-date set."""
    if column.name in existing:
        return
    op.add_column(table, column)
    existing.add(column.name)


def upgrade() -> None:
    existing = _existing_columns("store")
    _add_column_if_missing(
        "store",
        sa.Column(
            "receipt_logo_url", sa.String(500),
            nullable=True, server_default="",
        ),
        existing,
    )
    _add_column_if_missing(
        "store",
        sa.Column(
            "receipt_footer", sa.String(500),
            nullable=True, server_default="",
        ),
        existing,
    )
    _add_column_if_missing(
        "store",
        sa.Column(
            "receipt_tax_id", sa.String(40),
            nullable=True, server_default="",
        ),
        existing,
    )


def downgrade() -> None:
    op.drop_column("store", "receipt_tax_id")
    op.drop_column("store", "receipt_footer")
    op.drop_column("store", "receipt_logo_url")
