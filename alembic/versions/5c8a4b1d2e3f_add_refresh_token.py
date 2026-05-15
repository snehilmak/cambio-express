"""add refresh_token

Silent refresh of the 30-minute access JWT — paired with the
httpOnly access cookie added in PR #559. ``refresh_token`` is an
opaque, rotating, server-side-revocable secret; the SPA hits
``/auth/refresh`` when its access cookie 401s and the server
mints a fresh access + refresh pair, retiring the old refresh
row.

See ``api.Modules.Auth.Models.RefreshToken`` for the column
rationale (esp. ``revoked_at`` + ``rotated_to_id``, which back the
replay-detection logic).

Revision ID: 5c8a4b1d2e3f
Revises: 4b267ce786aa
Create Date: 2026-05-15 03:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5c8a4b1d2e3f'
down_revision: Union[str, None] = '4b267ce786aa'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "refresh_token",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("jti", sa.String(length=64),
                  nullable=False, unique=True),
        sa.Column("user_id", sa.Integer(),
                  sa.ForeignKey("user.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(),
                  nullable=False,
                  server_default=sa.func.current_timestamp()),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
        sa.Column("rotated_to_id", sa.Integer(),
                  sa.ForeignKey("refresh_token.id"), nullable=True),
    )
    op.create_index(
        "ix_refresh_token_jti", "refresh_token", ["jti"],
    )
    op.create_index(
        "ix_refresh_token_user_id", "refresh_token", ["user_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_refresh_token_user_id", table_name="refresh_token")
    op.drop_index("ix_refresh_token_jti", table_name="refresh_token")
    op.drop_table("refresh_token")
