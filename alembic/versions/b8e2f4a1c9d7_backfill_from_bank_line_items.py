"""backfill from_bank into daily_line_item

``from_bank`` (cash pulled from the bank into the drawer) becomes a
multi-entry line-item kind, like drops — a store can make several
bank runs a day. The ``daily_report.from_bank`` column stays as the
rolled-up total (``recompute_line_items_total`` keeps it in sync going
forward); this migration seeds the line items for history so the
existing single value shows up as one entry in the new box instead of
vanishing from the editor.

For every ``daily_report`` with ``from_bank > 0`` that has no
``from_bank`` line item yet, insert exactly one ``daily_line_item``
(kind='from_bank', amount=the stored total). Idempotent — re-running
skips reports that already have a from_bank line item, so a Render
replay can't double-count.

No schema change: ``daily_line_item.kind`` is a free-text column, so
the new kind needs no DDL. The column stays on ``daily_report``.

Revision ID: b8e2f4a1c9d7
Revises: a3d7e9f1c4b6
Create Date: 2026-08-08 00:00:00.000000

"""
from datetime import datetime
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b8e2f4a1c9d7'
down_revision: Union[str, None] = 'a3d7e9f1c4b6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def backfill_from_bank_line_items(bind: sa.engine.Connection) -> int:
    """Seed one ``from_bank`` line item per daily_report that has a
    positive stored total but no from_bank line item yet. Returns the
    number of rows seeded. Idempotent — the NOT EXISTS guard skips
    reports already seeded, so a replay adds nothing. Extracted from
    ``upgrade()`` so it's unit-testable against a plain connection."""
    now = datetime.utcnow()
    rows = bind.execute(
        sa.text(
            """
            SELECT dr.store_id, dr.report_date, dr.from_bank
            FROM daily_report dr
            WHERE dr.from_bank > 0
              AND NOT EXISTS (
                  SELECT 1 FROM daily_line_item li
                  WHERE li.store_id = dr.store_id
                    AND li.report_date = dr.report_date
                    AND li.kind = 'from_bank'
              )
            """
        )
    ).fetchall()

    if not rows:
        return 0

    insert = sa.text(
        """
        INSERT INTO daily_line_item
            (store_id, report_date, kind, at_time, amount, note, created_at)
        VALUES
            (:store_id, :report_date, 'from_bank', NULL, :amount, '', :created_at)
        """
    )
    for store_id, report_date, from_bank in rows:
        bind.execute(
            insert,
            {
                "store_id": store_id,
                "report_date": report_date,
                "amount": float(from_bank or 0),
                "created_at": now,
            },
        )
    return len(rows)


def upgrade() -> None:
    backfill_from_bank_line_items(op.get_bind())


def downgrade() -> None:
    # Remove only the seeded single-entry rows; a manual multi-run day
    # is indistinguishable after the fact, so we conservatively drop
    # all from_bank line items on downgrade. The daily_report.from_bank
    # column retains the last-computed total, so no dollar figure is
    # lost — the editor just reverts to treating it as a plain field.
    op.get_bind().execute(
        sa.text("DELETE FROM daily_line_item WHERE kind = 'from_bank'")
    )
