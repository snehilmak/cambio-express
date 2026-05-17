"""add user.notify_daily_summary + store.daily_summary_sent_for

Per-store nightly summary email (transfers + receipts +
disbursements for the prior day):

  - ``User.notify_daily_summary``      → per-user opt-out toggle.
    Default TRUE for admins/owners so close-out data reaches them
    out of the gate (matches the locked-day digest pattern).
  - ``Store.daily_summary_sent_for``   → dedup column. The cron
    stamps it on a successful pass so a re-run on the same day
    is a no-op.

Revision ID: 7a1c93f0d2b8
Revises: 4b267ce786aa
Create Date: 2026-05-17 02:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7a1c93f0d2b8'
down_revision: Union[str, None] = '5c8a4b1d2e3f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "user",
        sa.Column(
            "notify_daily_summary",
            sa.Boolean(),
            nullable=True,
            server_default=sa.true(),
        ),
    )
    op.add_column(
        "store",
        sa.Column(
            "daily_summary_sent_for",
            sa.Date(),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("store", "daily_summary_sent_for")
    op.drop_column("user", "notify_daily_summary")
