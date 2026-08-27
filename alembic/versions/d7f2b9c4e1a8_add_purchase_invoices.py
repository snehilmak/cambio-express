"""add purchase_invoice + purchase_invoice_line

Purchase invoices (Phase 2+ first item, owner-approved): vendor
invoices with optional price-book line links, hanging off the
Catalog module's Vendor + PriceBookItem tables.

Revision ID: d7f2b9c4e1a8
Revises: c9e5a2b7d4f1
Create Date: 2026-08-27 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision: str = 'd7f2b9c4e1a8'
down_revision: Union[str, None] = 'c9e5a2b7d4f1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(name: str) -> bool:
    bind = op.get_bind()
    return name in inspect(bind).get_table_names()


def upgrade() -> None:
    if not _has_table("purchase_invoice"):
        op.create_table(
            "purchase_invoice",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("store_id", sa.Integer(),
                      sa.ForeignKey("store.id"), nullable=False, index=True),
            sa.Column("vendor_id", sa.Integer(),
                      sa.ForeignKey("vendor.id"), nullable=False, index=True),
            sa.Column("invoice_number", sa.String(60), nullable=False),
            sa.Column("invoice_date", sa.Date(), nullable=False),
            sa.Column("due_date", sa.Date(), nullable=True),
            sa.Column("subtotal_cents", sa.BigInteger(), nullable=False,
                      server_default="0"),
            sa.Column("tax_cents", sa.BigInteger(), nullable=False,
                      server_default="0"),
            sa.Column("other_cents", sa.BigInteger(), nullable=False,
                      server_default="0"),
            sa.Column("status", sa.String(16), nullable=False,
                      server_default="open"),
            sa.Column("paid_on", sa.Date(), nullable=True),
            sa.Column("notes", sa.String(500), nullable=False,
                      server_default=""),
            sa.Column("created_by", sa.Integer(),
                      sa.ForeignKey("user.id"), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
            sa.UniqueConstraint("store_id", "vendor_id", "invoice_number"),
        )
    if not _has_table("purchase_invoice_line"):
        op.create_table(
            "purchase_invoice_line",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("store_id", sa.Integer(),
                      sa.ForeignKey("store.id"), nullable=False, index=True),
            sa.Column("invoice_id", sa.Integer(),
                      sa.ForeignKey("purchase_invoice.id"),
                      nullable=False, index=True),
            sa.Column("item_id", sa.Integer(),
                      sa.ForeignKey("price_book_item.id"),
                      nullable=True, index=True),
            sa.Column("description", sa.String(160), nullable=False,
                      server_default=""),
            sa.Column("quantity", sa.Float(), nullable=False,
                      server_default="1"),
            sa.Column("unit_cost_cents", sa.BigInteger(), nullable=False,
                      server_default="0"),
            sa.Column("line_total_cents", sa.BigInteger(), nullable=False,
                      server_default="0"),
        )


def downgrade() -> None:
    op.drop_table("purchase_invoice_line")
    op.drop_table("purchase_invoice")
