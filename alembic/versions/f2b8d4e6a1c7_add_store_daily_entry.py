"""Store Daily Book — one sheet per store per day (D-2).

Replaces the per-register "Day close" page as the daily workflow
for c-store / gas-station operators. Three columns that balance:
Sales, Tenders, Deposit & balance — with over/short falling out of
the difference.

`store_daily_entry_original` keeps what the POS reported for a
field before the operator edited it, so a correction never
destroys the register's own number.

Additive only: nothing is dropped, and `register_close` /
`department_sale` / `hourly_sale` are untouched — the Gilbarco
import keeps landing exactly where it does today, and its detail
becomes a section OF the day rather than a separate page.

Revision ID: f2b8d4e6a1c7
Revises: e7a3c5d1f9b4
"""
import sqlalchemy as sa
from alembic import op

from api.Modules.StoreBook.Models import COUNT_FIELDS, MONEY_FIELDS


revision = "f2b8d4e6a1c7"
down_revision = "e7a3c5d1f9b4"
branch_labels = None
depends_on = None


def _has_table(bind, name: str) -> bool:
    return name in sa.inspect(bind).get_table_names()


def upgrade() -> None:
    bind = op.get_bind()
    if not _has_table(bind, "store_daily_entry"):
        columns = [
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("store_id", sa.Integer(), nullable=False),
            sa.Column("entry_date", sa.Date(), nullable=False),
        ]
        # Money columns are generated from the model's own field
        # list, so the table and MONEY_FIELDS cannot drift apart.
        columns += [
            sa.Column(
                f"{key}_cents", sa.BigInteger(),
                nullable=False, server_default="0",
            )
            for key in MONEY_FIELDS
        ]
        for key in COUNT_FIELDS:
            # Gallons is volume (float); the rest are integer counts.
            col_type = (
                sa.Float() if key.endswith("gallons") else sa.Integer()
            )
            columns.append(
                sa.Column(
                    key, col_type, nullable=False, server_default="0",
                ),
            )
        columns += [
            sa.Column("notes", sa.Text(), nullable=False, server_default=""),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
            sa.Column("locked_at", sa.DateTime(), nullable=True),
            sa.Column("locked_by", sa.Integer(), nullable=True),
            sa.ForeignKeyConstraint(
                ["store_id"], ["store.id"], name="fk_sde_store",
            ),
            sa.ForeignKeyConstraint(
                ["locked_by"], ["user.id"], name="fk_sde_locked_by",
            ),
            sa.UniqueConstraint(
                "store_id", "entry_date", name="uq_sde_store_date",
            ),
        ]
        op.create_table("store_daily_entry", *columns)
        op.create_index(
            "ix_store_daily_entry_store_id", "store_daily_entry",
            ["store_id"],
        )
        op.create_index(
            "ix_store_daily_entry_entry_date", "store_daily_entry",
            ["entry_date"],
        )
        # The month-calendar query: one store, a date range.
        op.create_index(
            "ix_sde_store_date", "store_daily_entry",
            ["store_id", "entry_date"],
        )

    if not _has_table(bind, "store_daily_entry_original"):
        op.create_table(
            "store_daily_entry_original",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("entry_id", sa.Integer(), nullable=False),
            sa.Column("store_id", sa.Integer(), nullable=False),
            sa.Column("field_key", sa.String(length=40), nullable=False),
            sa.Column(
                "amount_cents", sa.BigInteger(),
                nullable=False, server_default="0",
            ),
            sa.Column(
                "source", sa.String(length=20),
                nullable=False, server_default="",
            ),
            sa.Column("imported_at", sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(
                ["entry_id"], ["store_daily_entry.id"],
                name="fk_sdeo_entry", ondelete="CASCADE",
            ),
            sa.UniqueConstraint(
                "entry_id", "field_key", name="uq_sdeo_entry_field",
            ),
        )
        op.create_index(
            "ix_sdeo_entry", "store_daily_entry_original", ["entry_id"],
        )
        op.create_index(
            "ix_sdeo_store", "store_daily_entry_original", ["store_id"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    for table in ("store_daily_entry_original", "store_daily_entry"):
        if _has_table(bind, table):
            op.drop_table(table)
