"""add user.notify_locked_day_digest

Owners + admins receive a one-page summary email when a daily book
is locked from the React editor. The toggle is opt-out (default
TRUE) so close-outs flow to owners out of the gate; the
notifications page lets recipients silence it.

Revision ID: 4b267ce786aa
Revises: 99691740424c
Create Date: 2026-05-12 20:44:55.917516

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4b267ce786aa'
down_revision: Union[str, None] = '99691740424c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "user",
        sa.Column(
            "notify_locked_day_digest",
            sa.Boolean(),
            nullable=True,
            server_default=sa.true(),
        ),
    )


def downgrade() -> None:
    op.drop_column("user", "notify_locked_day_digest")
