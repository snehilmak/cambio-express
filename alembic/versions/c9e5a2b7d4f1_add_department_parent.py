"""add department.parent_id (sub-departments)

P2-4: one-level-deep sub-departments — the planned nullable
``parent_id`` extension on the operator's department catalog.
Depth and cycle rules are enforced in the DayClose Service, not
the schema.

Revision ID: c9e5a2b7d4f1
Revises: b8d4f1a6c3e9
Create Date: 2026-08-23 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision: str = 'c9e5a2b7d4f1'
down_revision: Union[str, None] = 'b8d4f1a6c3e9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_column(table: str, column: str) -> bool:
    bind = op.get_bind()
    return column in {
        c["name"] for c in inspect(bind).get_columns(table)
    }


def upgrade() -> None:
    if not _has_column("department", "parent_id"):
        # Batch mode: SQLite can't ALTER in an FK constraint, so the
        # table is copy-and-moved there; Postgres runs plain ALTERs.
        with op.batch_alter_table("department", schema=None) as batch_op:
            batch_op.add_column(
                sa.Column("parent_id", sa.Integer(), nullable=True),
            )
            batch_op.create_foreign_key(
                "fk_department_parent_id", "department",
                ["parent_id"], ["id"],
            )


def downgrade() -> None:
    with op.batch_alter_table("department", schema=None) as batch_op:
        batch_op.drop_constraint(
            "fk_department_parent_id", type_="foreignkey",
        )
        batch_op.drop_column("parent_id")
