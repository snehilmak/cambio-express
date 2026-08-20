"""payroll cash/check split — columns + line-item backfill

Payroll becomes a pop-up with two line-item kinds:

  - ``payroll_cash`` → the existing ``daily_report.payroll_expense``
    column (still a daily disbursement, still feeds the monthly
    ``cash_payroll`` line).
  - ``payroll_check`` → NEW ``daily_report.payroll_check`` column,
    deliberately excluded from the daily totals (a payroll check
    doesn't move drawer cash) — it exists to feed the NEW
    ``monthly_financial.check_payroll`` P&L line.

This migration: (1) adds both columns (idempotent safe-adds), and
(2) backfills one ``payroll_cash`` line item per existing report
with ``payroll_expense > 0`` so the stored total shows up as an
entry in the new box instead of vanishing from the editor —
mirror of the from_bank (``b8e2f4a1c9d7``) and money_order
(``a9d5f1c7e3b8``) conversions, NOT EXISTS idempotency guard
included.

Revision ID: b3e7c1f9d5a2
Revises: a9d5f1c7e3b8
Create Date: 2026-08-20 00:00:00.000000

"""
from datetime import datetime
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision: str = 'b3e7c1f9d5a2'
down_revision: Union[str, None] = 'a9d5f1c7e3b8'
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


def backfill_payroll_cash_line_items(bind: sa.engine.Connection) -> int:
    """Seed one ``payroll_cash`` line item per daily_report with a
    positive stored ``payroll_expense`` but no payroll_cash line item
    yet. Returns rows seeded; idempotent via the NOT EXISTS guard."""
    now = datetime.utcnow()
    rows = bind.execute(
        sa.text(
            """
            SELECT dr.store_id, dr.report_date, dr.payroll_expense
            FROM daily_report dr
            WHERE dr.payroll_expense > 0
              AND NOT EXISTS (
                  SELECT 1 FROM daily_line_item li
                  WHERE li.store_id = dr.store_id
                    AND li.report_date = dr.report_date
                    AND li.kind = 'payroll_cash'
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
            (:store_id, :report_date, 'payroll_cash', NULL, :amount, '', :created_at)
        """
    )
    for store_id, report_date, payroll_expense in rows:
        bind.execute(
            insert,
            {
                "store_id": store_id,
                "report_date": report_date,
                "amount": float(payroll_expense or 0),
                "created_at": now,
            },
        )
    return len(rows)


def upgrade() -> None:
    _safe_add_column(
        "daily_report", "payroll_check",
        sa.Column("payroll_check", sa.Float(), nullable=True,
                  server_default="0"),
    )
    _safe_add_column(
        "monthly_financial", "check_payroll",
        sa.Column("check_payroll", sa.Float(), nullable=True,
                  server_default="0"),
    )
    backfill_payroll_cash_line_items(op.get_bind())


def downgrade() -> None:
    op.get_bind().execute(
        sa.text(
            "DELETE FROM daily_line_item "
            "WHERE kind IN ('payroll_cash', 'payroll_check')"
        )
    )
    with op.batch_alter_table("monthly_financial") as batch:
        batch.drop_column("check_payroll")
    with op.batch_alter_table("daily_report") as batch:
        batch.drop_column("payroll_check")
