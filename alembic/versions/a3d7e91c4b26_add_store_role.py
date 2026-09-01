"""add store_role, store_role_permission, user.store_role_id

Named reusable access roles (R-3).

Columns are spelled out literally here and never derived from the
models. A migration is immutable history: if it read its column
list from a live model, renaming a field later would silently
change what this revision creates, and a database rebuilt from
scratch would stop matching one migrated in place. (It also keeps
the model layer out of the Alembic loader, which ``init_db()``
runs during boot.) See CLAUDE.md "Migrations".

Revision ID: a3d7e91c4b26
Revises: f2b8d4e6a1c7
Create Date: 2026-09-01
"""
from alembic import op
import sqlalchemy as sa


revision = "a3d7e91c4b26"
down_revision = "f2b8d4e6a1c7"
branch_labels = None
depends_on = None


def _has_table(name: str) -> bool:
    bind = op.get_bind()
    return sa.inspect(bind).has_table(name)


def _has_column(table: str, column: str) -> bool:
    bind = op.get_bind()
    if not sa.inspect(bind).has_table(table):
        return False
    cols = {c["name"] for c in sa.inspect(bind).get_columns(table)}
    return column in cols


def upgrade() -> None:
    if not _has_table("store_role"):
        op.create_table(
            "store_role",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("store_id", sa.Integer(), nullable=False),
            sa.Column("name", sa.String(length=60), nullable=False),
            # No FK: user.store_role_id already points here, and an
            # FK back to user would close a DDL cycle SQLite cannot
            # order. Provenance only.
            sa.Column("created_by", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(
                ["store_id"], ["store.id"],
                name="fk_store_role_store_id",
            ),
            sa.PrimaryKeyConstraint("id", name="pk_store_role"),
            sa.UniqueConstraint(
                "store_id", "name", name="uq_store_role_store_name",
            ),
        )
        op.create_index(
            "ix_store_role_store_id", "store_role", ["store_id"],
        )

    if not _has_table("store_role_permission"):
        op.create_table(
            "store_role_permission",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("store_id", sa.Integer(), nullable=False),
            sa.Column("role_id", sa.Integer(), nullable=False),
            sa.Column("resource", sa.String(length=40), nullable=False),
            sa.Column("action", sa.String(length=20), nullable=False),
            sa.ForeignKeyConstraint(
                ["store_id"], ["store.id"],
                name="fk_store_role_permission_store_id",
            ),
            sa.ForeignKeyConstraint(
                ["role_id"], ["store_role.id"],
                name="fk_store_role_permission_role_id",
                ondelete="CASCADE",
            ),
            sa.PrimaryKeyConstraint("id", name="pk_store_role_permission"),
            sa.UniqueConstraint(
                "role_id", "resource", "action",
                name="uq_store_role_permission_grant",
            ),
        )
        op.create_index(
            "ix_store_role_permission_role_id",
            "store_role_permission", ["role_id"],
        )
        op.create_index(
            "ix_store_role_permission_store_id",
            "store_role_permission", ["store_id"],
        )

    if not _has_column("user", "store_role_id"):
        # Batch mode so SQLite can add the FK; a no-op elsewhere.
        with op.batch_alter_table("user") as batch:
            batch.add_column(
                sa.Column("store_role_id", sa.Integer(), nullable=True),
            )
            batch.create_foreign_key(
                "fk_user_store_role_id", "store_role",
                ["store_role_id"], ["id"],
            )
        op.create_index(
            "ix_user_store_role_id", "user", ["store_role_id"],
        )


def downgrade() -> None:
    # Drop the reference before the table it points at.
    if _has_column("user", "store_role_id"):
        op.drop_index("ix_user_store_role_id", table_name="user")
        with op.batch_alter_table("user") as batch:
            batch.drop_constraint("fk_user_store_role_id", type_="foreignkey")
            batch.drop_column("store_role_id")
    if _has_table("store_role_permission"):
        op.drop_index(
            "ix_store_role_permission_store_id",
            table_name="store_role_permission",
        )
        op.drop_index(
            "ix_store_role_permission_role_id",
            table_name="store_role_permission",
        )
        op.drop_table("store_role_permission")
    if _has_table("store_role"):
        op.drop_index("ix_store_role_store_id", table_name="store_role")
        op.drop_table("store_role")
