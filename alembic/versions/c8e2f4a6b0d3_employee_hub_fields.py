"""store_employee: login link + HR/personal fields (E-1)

The unified Employees hub makes ``store_employee`` the canonical
HR record for a person, with an optional 1:1 link to their login
account. Adds:

* ``user_id``          — nullable unique FK → ``user.id``. One
                         login belongs to at most one person.
* ``hired_on`` / ``date_of_birth`` — HR dates.
* ``email`` / ``phone`` / ``address_line1`` / ``address_line2``
                       — contact details (empty-string defaults,
                         same convention as ``store.email``).
* ``payroll_schedule`` — display metadata (weekly / biweekly /
                         semimonthly / monthly), empty = unset.

Backfill: auto-link existing login accounts to roster rows where
``lower(trim(user.full_name)) == lower(trim(store_employee.name))``
within the same store AND the match is unambiguous (exactly one
row on each side carries that name). Near-miss names stay
unlinked — the Employees hub offers a manual Link action, so a
wrong guess here would be worse than no guess.

Revision ID: c8e2f4a6b0d3
Revises: b5d1f7a3c9e6
Create Date: 2026-08-30 20:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision: str = 'c8e2f4a6b0d3'
down_revision: Union[str, None] = 'b5d1f7a3c9e6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_column(table: str, column: str) -> bool:
    bind = op.get_bind()
    cols = {c["name"] for c in inspect(bind).get_columns(table)}
    return column in cols


def _columns() -> list[sa.Column]:
    # Factory so upgrade/downgrade never reuse a Column instance.
    return [
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("hired_on", sa.Date(), nullable=True),
        sa.Column("date_of_birth", sa.Date(), nullable=True),
        sa.Column("email", sa.String(length=255), nullable=False,
                  server_default=""),
        sa.Column("phone", sa.String(length=40), nullable=False,
                  server_default=""),
        sa.Column("address_line1", sa.String(length=255), nullable=False,
                  server_default=""),
        sa.Column("address_line2", sa.String(length=255), nullable=False,
                  server_default=""),
        sa.Column("payroll_schedule", sa.String(length=20), nullable=False,
                  server_default=""),
    ]


def upgrade() -> None:
    adding_user_id = not _has_column("store_employee", "user_id")
    with op.batch_alter_table("store_employee") as batch:
        for col in _columns():
            if not _has_column("store_employee", col.name):
                batch.add_column(col)
    if adding_user_id:
        # Named FK in its own batch pass — SQLite batch mode
        # refuses anonymous constraints.
        with op.batch_alter_table("store_employee") as batch:
            batch.create_foreign_key(
                "fk_store_employee_user_id", "user",
                ["user_id"], ["id"],
            )

    # Unique index on user_id (nullable-unique: multiple NULLs OK
    # on both SQLite and Postgres).
    bind = op.get_bind()
    idx_names = {i["name"] for i in inspect(bind).get_indexes("store_employee")}
    if "ix_store_employee_user_id" not in idx_names:
        op.create_index(
            "ix_store_employee_user_id", "store_employee", ["user_id"],
            unique=True,
        )

    # Backfill: unambiguous exact-name links per store.
    bind.execute(sa.text("""
        UPDATE store_employee SET user_id = (
            SELECT u.id FROM "user" u
            WHERE u.store_id = store_employee.store_id
              AND u.role IN ('admin', 'employee')
              AND LOWER(TRIM(u.full_name)) = LOWER(TRIM(store_employee.name))
              AND LOWER(TRIM(u.full_name)) != ''
              AND NOT EXISTS (
                  SELECT 1 FROM store_employee se2
                  WHERE se2.user_id = u.id
              )
              AND (SELECT COUNT(*) FROM "user" u2
                   WHERE u2.store_id = store_employee.store_id
                     AND u2.role IN ('admin', 'employee')
                     AND LOWER(TRIM(u2.full_name)) =
                         LOWER(TRIM(store_employee.name))) = 1
              AND (SELECT COUNT(*) FROM store_employee se3
                   WHERE se3.store_id = store_employee.store_id
                     AND LOWER(TRIM(se3.name)) =
                         LOWER(TRIM(store_employee.name))) = 1
        )
        WHERE user_id IS NULL
    """))


def downgrade() -> None:
    bind = op.get_bind()
    idx_names = {i["name"] for i in inspect(bind).get_indexes("store_employee")}
    if "ix_store_employee_user_id" in idx_names:
        op.drop_index("ix_store_employee_user_id", "store_employee")
    with op.batch_alter_table("store_employee") as batch:
        for col in _columns():
            if _has_column("store_employee", col.name):
                batch.drop_column(col.name)
