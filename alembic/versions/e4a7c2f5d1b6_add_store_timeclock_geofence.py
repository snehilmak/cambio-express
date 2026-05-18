"""add store timeclock geofence

Anti-buddy-punching companion to the passkey gate (PR #609).
Refuses time-clock punches when the cashier's device is more
than ``timeclock_geofence_radius_m`` away from the store's
configured lat/lng. The passkey gate proves "this is the right
person"; the geofence proves "they're physically at the store".

Schema additions
----------------
* ``timeclock_geofence_lat`` (Float, nullable)
* ``timeclock_geofence_lng`` (Float, nullable)
* ``timeclock_geofence_radius_m`` (Integer, default 100)
* ``timeclock_require_geofence`` (Boolean, default False)

Default-off so existing stores keep working. The admin sets
the geofence by tapping "Use current location" at the store
terminal — captures the browser's GPS coordinates once, then
flips the toggle.

Upgrade is idempotent — uses the ``_safe_add_column`` pattern
that's been carrying the recent revisions through Render's
DuplicateColumn quirk.

Revision ID: e4a7c2f5d1b6
Revises: d2e6a4f1b8c3
Create Date: 2026-05-18 19:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision: str = 'e4a7c2f5d1b6'
down_revision: Union[str, None] = 'd2e6a4f1b8c3'
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
        "store", "timeclock_geofence_lat",
        sa.Column("timeclock_geofence_lat", sa.Float(), nullable=True),
    )
    _safe_add_column(
        "store", "timeclock_geofence_lng",
        sa.Column("timeclock_geofence_lng", sa.Float(), nullable=True),
    )
    _safe_add_column(
        "store", "timeclock_geofence_radius_m",
        sa.Column(
            "timeclock_geofence_radius_m", sa.Integer(),
            nullable=True, server_default="100",
        ),
    )
    _safe_add_column(
        "store", "timeclock_require_geofence",
        sa.Column(
            "timeclock_require_geofence", sa.Boolean(),
            nullable=True, server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    op.drop_column("store", "timeclock_require_geofence")
    op.drop_column("store", "timeclock_geofence_radius_m")
    op.drop_column("store", "timeclock_geofence_lng")
    op.drop_column("store", "timeclock_geofence_lat")
