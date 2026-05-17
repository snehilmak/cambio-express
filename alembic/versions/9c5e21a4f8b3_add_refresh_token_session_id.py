"""add session_id + device metadata to refresh_token

Lets the SPA show a "you're signed in on N devices" panel and
revoke individual sessions. The new columns:

* ``session_id`` — stable UUID for one login session. Minted on
  ``Services.refresh.issue`` (called from every login path) and
  COPIED forward through every ``rotate()`` call. The full chain
  of refresh tokens for one browser shares one ``session_id``.
* ``user_agent`` — raw User-Agent header, captured per row. The
  SPA parses it into "Chrome on macOS" client-side.
* ``ip_address`` — captured per row. Reflects the most recent
  refresh (a session that started at home + refreshed at a coffee
  shop shows the coffee-shop IP after rotation).

Existing rows get filled in lazily — ``session_id`` is nullable
and the list endpoint groups rows by ``(user_id, session_id)``
treating NULL as a singleton "legacy" session for each user.

Revision ID: 9c5e21a4f8b3
Revises: 7a1c93f0d2b8
Create Date: 2026-05-17 04:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9c5e21a4f8b3'
down_revision: Union[str, None] = '7a1c93f0d2b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "refresh_token",
        sa.Column("session_id", sa.String(36), nullable=True),
    )
    op.add_column(
        "refresh_token",
        sa.Column("user_agent", sa.String(255), nullable=True),
    )
    op.add_column(
        "refresh_token",
        sa.Column("ip_address", sa.String(45), nullable=True),
    )
    # Index by (user_id, session_id) — the "list my sessions"
    # query groups rows by this pair.
    op.create_index(
        "ix_refresh_token_user_session",
        "refresh_token",
        ["user_id", "session_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_refresh_token_user_session", table_name="refresh_token",
    )
    op.drop_column("refresh_token", "ip_address")
    op.drop_column("refresh_token", "user_agent")
    op.drop_column("refresh_token", "session_id")
