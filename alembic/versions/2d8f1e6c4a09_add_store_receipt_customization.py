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

Revision ID: 2d8f1e6c4a09
Revises: 9c5e21a4f8b3
Create Date: 2026-05-17 05:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2d8f1e6c4a09'
down_revision: Union[str, None] = '9c5e21a4f8b3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "store",
        sa.Column(
            "receipt_logo_url", sa.String(500),
            nullable=True, server_default="",
        ),
    )
    op.add_column(
        "store",
        sa.Column(
            "receipt_footer", sa.String(500),
            nullable=True, server_default="",
        ),
    )
    op.add_column(
        "store",
        sa.Column(
            "receipt_tax_id", sa.String(40),
            nullable=True, server_default="",
        ),
    )


def downgrade() -> None:
    op.drop_column("store", "receipt_tax_id")
    op.drop_column("store", "receipt_footer")
    op.drop_column("store", "receipt_logo_url")
