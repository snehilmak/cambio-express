"""add lottery tables (P1-6 — the c-store wedge feature)

Three tables: lottery_game (game catalog per store), lottery_pack
(pack lifecycle received → active → settled/returned), and
lottery_day_count (day-close ticket counts, one row per
store/date/pack). Money is integer cents from day one — no Float
columns (P0-3 convention).

Revision ID: c4e8a2d6f1b3
Revises: b9d5e1f7a3c2
Create Date: 2026-08-22 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision: str = 'c4e8a2d6f1b3'
down_revision: Union[str, None] = 'b9d5e1f7a3c2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(name: str) -> bool:
    bind = op.get_bind()
    return name in inspect(bind).get_table_names()


def upgrade() -> None:
    if not _has_table("lottery_game"):
        op.create_table(
            "lottery_game",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("store_id", sa.Integer(),
                      sa.ForeignKey("store.id"), nullable=False, index=True),
            sa.Column("game_number", sa.String(20), nullable=False),
            sa.Column("name", sa.String(120), nullable=False),
            sa.Column("ticket_price_cents", sa.BigInteger(),
                      nullable=False, server_default="0"),
            sa.Column("tickets_per_pack", sa.Integer(),
                      nullable=False, server_default="0"),
            sa.Column("is_active", sa.Boolean(),
                      nullable=False, server_default=sa.true()),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.UniqueConstraint("store_id", "game_number"),
        )
    if not _has_table("lottery_pack"):
        op.create_table(
            "lottery_pack",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("store_id", sa.Integer(),
                      sa.ForeignKey("store.id"), nullable=False, index=True),
            sa.Column("game_id", sa.Integer(),
                      sa.ForeignKey("lottery_game.id"),
                      nullable=False, index=True),
            sa.Column("pack_number", sa.String(40), nullable=False),
            sa.Column("status", sa.String(16),
                      nullable=False, server_default="received"),
            sa.Column("bin_number", sa.String(10), server_default=""),
            sa.Column("received_on", sa.Date(), nullable=True),
            sa.Column("activated_on", sa.Date(), nullable=True),
            sa.Column("settled_on", sa.Date(), nullable=True),
            sa.Column("opening_ticket", sa.Integer(),
                      nullable=False, server_default="0"),
            sa.Column("created_by", sa.Integer(),
                      sa.ForeignKey("user.id"), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.UniqueConstraint("store_id", "game_id", "pack_number"),
        )
    if not _has_table("lottery_day_count"):
        op.create_table(
            "lottery_day_count",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("store_id", sa.Integer(),
                      sa.ForeignKey("store.id"), nullable=False, index=True),
            sa.Column("report_date", sa.Date(), nullable=False),
            sa.Column("pack_id", sa.Integer(),
                      sa.ForeignKey("lottery_pack.id"),
                      nullable=False, index=True),
            sa.Column("closing_ticket", sa.Integer(), nullable=False),
            sa.Column("created_by", sa.Integer(),
                      sa.ForeignKey("user.id"), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.UniqueConstraint("store_id", "report_date", "pack_id"),
        )


def downgrade() -> None:
    op.drop_table("lottery_day_count")
    op.drop_table("lottery_pack")
    op.drop_table("lottery_game")
