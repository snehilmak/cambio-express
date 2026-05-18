"""add timeclock passkey gating

Anti-buddy-punching: a store can require a WebAuthn assertion
(Windows Hello, Touch ID, Face ID, hardware key) on every
clock-in / clock-out. The roster member registers their passkey
once with the admin at the punch terminal; afterwards every
punch demands a fresh assertion before the entry lands.

Schema additions
----------------
* ``store.timeclock_require_passkey`` — per-store opt-in
  Boolean. Default False so existing stores keep working.
  Flipping to True without any registered roster passkeys
  blocks everyone from punching, so the admin UI exposes a
  registration page first.

* ``store_employee_passkey`` — one row per roster member
  passkey. Mirrors the shape of the existing ``Passkey``
  table but keyed on ``store_employee_id`` (the human roster
  row), not ``user.id`` (the login account). This is the key
  design choice: multiple cashiers share one ``employee``
  ``User`` login in this codebase, so user→passkey doesn't
  identify the cashier — roster→passkey does.

  We keep v1 to one passkey per roster member; the unique
  index on ``store_employee_id`` enforces that. If a cashier
  upgrades devices, the admin removes the old row and
  re-registers.

Upgrade is idempotent — uses the same ``_has_column`` /
``_table_exists`` guards as the rest of the recent revisions.

Revision ID: b3d5e7f9a2c1
Revises: a9c2b4e7d1f5
Create Date: 2026-05-18 07:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision: str = 'b3d5e7f9a2c1'
down_revision: Union[str, None] = 'a9c2b4e7d1f5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_column(table: str, column: str) -> bool:
    bind = op.get_bind()
    cols = {c["name"] for c in inspect(bind).get_columns(table)}
    return column in cols


def _table_exists(name: str) -> bool:
    bind = op.get_bind()
    return name in set(inspect(bind).get_table_names())


def _safe_add_column(table: str, column_name: str, column) -> None:
    """Idempotent ``add_column`` — see the matching helper in
    revision ``a9c2b4e7d1f5`` for the rationale. Inspector
    cache misses in prod left us with a duplicate-column
    crash that the bare check couldn't catch."""
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
        "store", "timeclock_require_passkey",
        sa.Column(
            "timeclock_require_passkey", sa.Boolean(),
            nullable=True, server_default=sa.false(),
        ),
    )

    if not _table_exists("store_employee_passkey"):
        op.create_table(
            "store_employee_passkey",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column(
                "store_id", sa.Integer,
                sa.ForeignKey("store.id"), nullable=False, index=True,
            ),
            # One passkey per roster row in v1. If the cashier
            # gets a new device the admin deletes + re-registers.
            sa.Column(
                "store_employee_id", sa.Integer,
                sa.ForeignKey("store_employee.id"),
                nullable=False, unique=True,
            ),
            sa.Column(
                "credential_id", sa.LargeBinary,
                unique=True, nullable=False,
            ),
            sa.Column("public_key",  sa.LargeBinary, nullable=False),
            sa.Column("sign_count",  sa.Integer, nullable=False,
                      server_default="0"),
            sa.Column("aaguid",      sa.String(64),
                      nullable=True, server_default=""),
            sa.Column("name",        sa.String(120),
                      nullable=True, server_default=""),
            sa.Column("registered_at", sa.DateTime, nullable=True),
            sa.Column("last_used_at",  sa.DateTime, nullable=True),
            sa.Column(
                "registered_by_user_id", sa.Integer,
                sa.ForeignKey("user.id"), nullable=True,
            ),
        )


def downgrade() -> None:
    op.drop_table("store_employee_passkey")
    op.drop_column("store", "timeclock_require_passkey")
