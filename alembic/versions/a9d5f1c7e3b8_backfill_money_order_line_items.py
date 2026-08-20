"""backfill money_order into daily_line_item

``money_order`` (money orders sold) becomes a multi-entry line-item
kind: some operators enter one aggregate total for the day, others
prefer one entry per money order — line items support both. The
``daily_report.money_order`` column stays as the rolled-up total
(``recompute_line_items_total`` keeps it in sync going forward);
this migration seeds the line items for history so the existing
single value shows up as one entry in the new box instead of
vanishing from the editor.

For every ``daily_report`` with ``money_order > 0`` that has no
``money_order`` line item yet, insert exactly one ``daily_line_item``
(kind='money_order', amount=the stored total). Idempotent — re-running
skips reports that already have a money_order line item, so a Render
replay can't double-count. Mirrors the ``from_bank`` conversion
(revision ``b8e2f4a1c9d7``).

No schema change: ``daily_line_item.kind`` is a free-text column, so
the new kind needs no DDL. The column stays on ``daily_report``.

Revision ID: a9d5f1c7e3b8
Revises: f6c2a8e4d9b1
Create Date: 2026-08-20 00:00:00.000000

"""
from datetime import datetime
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a9d5f1c7e3b8'
down_revision: Union[str, None] = 'f6c2a8e4d9b1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def backfill_money_order_line_items(bind: sa.engine.Connection) -> int:
    """Seed one ``money_order`` line item per daily_report that has a
    positive stored total but no money_order line item yet. Returns
    the number of rows seeded. Idempotent — the NOT EXISTS guard skips
    reports already seeded, so a replay adds nothing. Extracted from
    ``upgrade()`` so it's unit-testable against a plain connection."""
    now = datetime.utcnow()
    rows = bind.execute(
        sa.text(
            """
            SELECT dr.store_id, dr.report_date, dr.money_order
            FROM daily_report dr
            WHERE dr.money_order > 0
              AND NOT EXISTS (
                  SELECT 1 FROM daily_line_item li
                  WHERE li.store_id = dr.store_id
                    AND li.report_date = dr.report_date
                    AND li.kind = 'money_order'
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
            (:store_id, :report_date, 'money_order', NULL, :amount, '', :created_at)
        """
    )
    for store_id, report_date, money_order in rows:
        bind.execute(
            insert,
            {
                "store_id": store_id,
                "report_date": report_date,
                "amount": float(money_order or 0),
                "created_at": now,
            },
        )
    return len(rows)


def upgrade() -> None:
    backfill_money_order_line_items(op.get_bind())


def downgrade() -> None:
    # Remove only the seeded rows conservatively: a manual multi-entry
    # day is indistinguishable after the fact, so downgrade drops all
    # money_order line items. The daily_report.money_order column
    # retains the last-computed total, so no dollar figure is lost —
    # the editor just reverts to treating it as a plain field.
    op.get_bind().execute(
        sa.text("DELETE FROM daily_line_item WHERE kind = 'money_order'")
    )
