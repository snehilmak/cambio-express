"""add user.notify_* push toggles

Per-kind push-channel toggles next to the existing email toggles.
Each user gets a default-True boolean per notification kind that
the dispatcher reads before fanning out to that user's
PushSubscription rows.

Schema additions
----------------
* ``user.notify_trial_reminders_push``   (Boolean, default True)
* ``user.notify_announcement_push``      (Boolean, default True)
* ``user.notify_locked_day_digest_push`` (Boolean, default True)
* ``user.notify_daily_summary_push``     (Boolean, default True)

Default-True (opt-out) so a user who flips the channel ON via the
"Enable browser notifications" CTA immediately starts getting
every kind; they can then opt out per-kind from the same page.

Upgrade is idempotent — uses the ``_safe_add_column`` pattern
shared by the other recent revisions to survive Render's
DuplicateColumn replay quirk on Postgres.

Revision ID: a2b3c4d5e6f7
Revises: f1a8b3d92c47
Create Date: 2026-05-19 14:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision: str = 'a2b3c4d5e6f7'
down_revision: Union[str, None] = 'f1a8b3d92c47'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_column(table: str, column: str) -> bool:
    bind = op.get_bind()
    cols = {c["name"] for c in inspect(bind).get_columns(table)}
    return column in cols


def _safe_add_column(table: str, column_name: str, column) -> None:
    if _has_column(table, column_name):
        return
    try:
        op.add_column(table, column)
    except Exception as exc:
        msg = str(exc).lower()
        if "already exists" in msg or "duplicate column" in msg:
            return
        raise


def upgrade() -> None:
    _safe_add_column(
        "user", "notify_trial_reminders_push",
        sa.Column(
            "notify_trial_reminders_push", sa.Boolean(),
            nullable=True, server_default=sa.true(),
        ),
    )
    _safe_add_column(
        "user", "notify_announcement_push",
        sa.Column(
            "notify_announcement_push", sa.Boolean(),
            nullable=True, server_default=sa.true(),
        ),
    )
    _safe_add_column(
        "user", "notify_locked_day_digest_push",
        sa.Column(
            "notify_locked_day_digest_push", sa.Boolean(),
            nullable=True, server_default=sa.true(),
        ),
    )
    _safe_add_column(
        "user", "notify_daily_summary_push",
        sa.Column(
            "notify_daily_summary_push", sa.Boolean(),
            nullable=True, server_default=sa.true(),
        ),
    )


def downgrade() -> None:
    op.drop_column("user", "notify_daily_summary_push")
    op.drop_column("user", "notify_locked_day_digest_push")
    op.drop_column("user", "notify_announcement_push")
    op.drop_column("user", "notify_trial_reminders_push")
