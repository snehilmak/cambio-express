"""Persist POS transactions, lines and tenders (G-5).

PJR events were parsed, rolled into day aggregates, and the detail
thrown away — an operator could see a day's totals but never the
transaction behind them. These three tables keep the event itself,
including lines the register cancelled (voided items), which are
stored with `status='cancel'` and excluded from every money total.

Additive only: no existing column changes, nothing dropped. Rows
are derived from the staged journal originals, so the tables start
empty and fill on the next commit of a business day.

Revision ID: e7a3c5d1f9b4
Revises: d4b7e1c9a2f5
"""
import sqlalchemy as sa
from alembic import op


revision = "e7a3c5d1f9b4"
down_revision = "d4b7e1c9a2f5"
branch_labels = None
depends_on = None


def _has_table(bind, name: str) -> bool:
    return name in sa.inspect(bind).get_table_names()


def upgrade() -> None:
    bind = op.get_bind()

    if not _has_table(bind, "pos_transaction"):
        op.create_table(
            "pos_transaction",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("store_id", sa.Integer(), nullable=False),
            sa.Column("business_date", sa.Date(), nullable=False),
            sa.Column("source_file", sa.String(length=120), nullable=False),
            sa.Column("kind", sa.String(length=16), nullable=False, server_default=""),
            sa.Column("register_id", sa.String(length=20), nullable=False, server_default=""),
            sa.Column("cashier_id", sa.String(length=20), nullable=False, server_default=""),
            sa.Column("till_id", sa.String(length=20), nullable=False, server_default=""),
            sa.Column("transaction_no", sa.String(length=30), nullable=False, server_default=""),
            sa.Column("event_sequence_id", sa.String(length=20), nullable=False, server_default=""),
            sa.Column("started_at", sa.DateTime(), nullable=True),
            sa.Column("ended_at", sa.DateTime(), nullable=True),
            sa.Column("receipt_at", sa.DateTime(), nullable=True),
            sa.Column("event_hour", sa.Integer(), nullable=True),
            sa.Column("outside", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("training_mode", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("offline", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("suspended", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("gross_cents", sa.BigInteger(), nullable=False, server_default="0"),
            sa.Column("net_cents", sa.BigInteger(), nullable=False, server_default="0"),
            sa.Column("tax_cents", sa.BigInteger(), nullable=False, server_default="0"),
            sa.Column("grand_total_cents", sa.BigInteger(), nullable=False, server_default="0"),
            sa.Column("has_voided_line", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.ForeignKeyConstraint(
                ["store_id"], ["store.id"], name="fk_pos_txn_store",
            ),
            sa.UniqueConstraint(
                "store_id", "source_file", name="uq_pos_txn_source_file",
            ),
        )
        op.create_index(
            "ix_pos_transaction_store_id", "pos_transaction", ["store_id"],
        )
        op.create_index(
            "ix_pos_transaction_business_date", "pos_transaction",
            ["business_date"],
        )
        # The list view's default query: one store, one day, newest
        # first. Without this it table-scans every transaction the
        # store has ever recorded.
        op.create_index(
            "ix_pos_txn_store_date", "pos_transaction",
            ["store_id", "business_date"],
        )

    if not _has_table(bind, "pos_transaction_line"):
        op.create_table(
            "pos_transaction_line",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("transaction_id", sa.Integer(), nullable=False),
            sa.Column("store_id", sa.Integer(), nullable=False),
            sa.Column("business_date", sa.Date(), nullable=False),
            sa.Column("line_seq", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("status", sa.String(length=10), nullable=False, server_default="normal"),
            sa.Column("pos_code", sa.String(length=30), nullable=False, server_default=""),
            sa.Column("pos_code_format", sa.String(length=20), nullable=False, server_default=""),
            sa.Column("description", sa.String(length=160), nullable=False, server_default=""),
            sa.Column("entry_method", sa.String(length=20), nullable=False, server_default=""),
            sa.Column("merchandise_code", sa.String(length=20), nullable=False, server_default=""),
            sa.Column("selling_units", sa.String(length=20), nullable=False, server_default=""),
            sa.Column("tax_level_id", sa.String(length=20), nullable=False, server_default=""),
            sa.Column("quantity", sa.Float(), nullable=False, server_default="0"),
            sa.Column("amount_cents", sa.BigInteger(), nullable=False, server_default="0"),
            sa.Column("actual_price_cents", sa.BigInteger(), nullable=False, server_default="0"),
            sa.Column("regular_price_cents", sa.BigInteger(), nullable=False, server_default="0"),
            sa.Column("is_fuel", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("fuel_grade_id", sa.String(length=10), nullable=False, server_default=""),
            sa.Column("fuel_position", sa.String(length=10), nullable=False, server_default=""),
            sa.Column("gallons", sa.Float(), nullable=False, server_default="0"),
            sa.ForeignKeyConstraint(
                ["transaction_id"], ["pos_transaction.id"],
                name="fk_pos_txn_line_txn", ondelete="CASCADE",
            ),
        )
        op.create_index(
            "ix_pos_txn_line_txn", "pos_transaction_line",
            ["transaction_id"],
        )
        op.create_index(
            "ix_pos_txn_line_store_date", "pos_transaction_line",
            ["store_id", "business_date"],
        )
        # "Where did this UPC sell?" across days.
        op.create_index(
            "ix_pos_txn_line_pos_code", "pos_transaction_line",
            ["store_id", "pos_code"],
        )

    if not _has_table(bind, "pos_transaction_tender"):
        op.create_table(
            "pos_transaction_tender",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("transaction_id", sa.Integer(), nullable=False),
            sa.Column("store_id", sa.Integer(), nullable=False),
            sa.Column("business_date", sa.Date(), nullable=False),
            sa.Column("status", sa.String(length=10), nullable=False, server_default="normal"),
            sa.Column("code", sa.String(length=30), nullable=False, server_default=""),
            sa.Column("sub_code", sa.String(length=30), nullable=False, server_default=""),
            sa.Column("amount_cents", sa.BigInteger(), nullable=False, server_default="0"),
            sa.Column("is_change", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.ForeignKeyConstraint(
                ["transaction_id"], ["pos_transaction.id"],
                name="fk_pos_txn_tender_txn", ondelete="CASCADE",
            ),
        )
        op.create_index(
            "ix_pos_txn_tender_txn", "pos_transaction_tender",
            ["transaction_id"],
        )
        op.create_index(
            "ix_pos_txn_tender_store_date", "pos_transaction_tender",
            ["store_id", "business_date"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    # Children first — the FKs point at pos_transaction.
    for table in (
        "pos_transaction_tender", "pos_transaction_line", "pos_transaction",
    ):
        if _has_table(bind, table):
            op.drop_table(table)
