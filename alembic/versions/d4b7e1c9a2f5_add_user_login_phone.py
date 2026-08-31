"""Add User.login_phone — canonical phone for sign-in (L-2).

Sign-in accepts a phone number, which means matching the digits a
person types against the digits we stored. `User.phone` holds the
number as the operator typed it ("(555) 123-4567"), so it can't
serve that lookup; `login_phone` holds the same number normalised to
digits (NANP country code dropped) and carries the index.

Backfill uses the same normalisation as
`api/Modules/Auth/Services/identity.normalize_phone`, in SQL so it
runs on SQLite and Postgres alike: strip the punctuation we actually
see in this column, then drop a leading "1" from an 11-digit result.

Revision ID: d4b7e1c9a2f5
Revises: c8e2f4a6b0d3
"""
import sqlalchemy as sa
from alembic import op


revision = "d4b7e1c9a2f5"
down_revision = "c8e2f4a6b0d3"
branch_labels = None
depends_on = None


def _has_column(bind, table: str, column: str) -> bool:
    return column in {
        c["name"] for c in sa.inspect(bind).get_columns(table)
    }


# Nested REPLACE() rather than a regex: SQLite has no regexp_replace
# built in, so this is the portable way to strip formatting.
_DIGITS = (
    "REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE("
    "COALESCE(phone, ''), ' ', ''), '(', ''), ')', ''), '-', ''),"
    " '.', ''), '+', '')"
)


def upgrade() -> None:
    bind = op.get_bind()
    if not _has_column(bind, "user", "login_phone"):
        with op.batch_alter_table("user") as batch:
            batch.add_column(
                sa.Column(
                    "login_phone", sa.String(length=20),
                    nullable=True, server_default="",
                ),
            )
        op.create_index("ix_user_login_phone", "user", ["login_phone"])

    # Backfill from the display column. Only rows whose stripped
    # value is all digits and long enough to be a phone number —
    # anything else (extensions, free text) stays blank rather than
    # becoming a login identifier nobody intended.
    op.execute(f"""
        UPDATE "user"
        SET login_phone = CASE
            WHEN LENGTH({_DIGITS}) = 11 AND {_DIGITS} LIKE '1%'
                THEN SUBSTR({_DIGITS}, 2)
            ELSE {_DIGITS}
        END
        WHERE COALESCE(phone, '') <> ''
          AND LENGTH({_DIGITS}) >= 7
          AND {_DIGITS} NOT GLOB '*[^0-9]*'
    """ if bind.dialect.name == "sqlite" else f"""
        UPDATE "user"
        SET login_phone = CASE
            WHEN LENGTH({_DIGITS}) = 11 AND {_DIGITS} LIKE '1%'
                THEN SUBSTR({_DIGITS}, 2)
            ELSE {_DIGITS}
        END
        WHERE COALESCE(phone, '') <> ''
          AND LENGTH({_DIGITS}) >= 7
          AND {_DIGITS} ~ '^[0-9]+$'
    """)

    op.execute("UPDATE \"user\" SET login_phone = '' "
               "WHERE login_phone IS NULL")


def downgrade() -> None:
    bind = op.get_bind()
    if _has_column(bind, "user", "login_phone"):
        op.drop_index("ix_user_login_phone", table_name="user")
        with op.batch_alter_table("user") as batch:
            batch.drop_column("login_phone")
