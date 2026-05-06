"""DailyLineItem SQL helpers.

Each line item belongs to a `(store_id, report_date)` pair and is
discriminated by `kind` (cash_purchase, cash_expense, etc.). The
`kind` slug isn't a DB enum so new kinds can be introduced with
zero migration.
"""
from datetime import date
from typing import Iterable

from sqlalchemy import func
from sqlalchemy.orm import Session

from api.Modules.DailyBook.Models import DailyLineItem


def list_line_items(
    db: Session, store_id: int, report_date: date,
    *, kinds: Iterable[str] | None = None,
) -> list[DailyLineItem]:
    """Line items for a given (store, date), ordered by at_time asc
    (chronological — matches how the cashier sees them in the form)
    and id asc tie-break for stable rendering. Optional `kinds`
    filter scopes to specific line types."""
    q = db.query(DailyLineItem).filter(
        DailyLineItem.store_id == store_id,
        DailyLineItem.report_date == report_date,
    )
    if kinds is not None:
        kinds_list = list(kinds)
        if not kinds_list:
            return []
        q = q.filter(DailyLineItem.kind.in_(kinds_list))
    return q.order_by(
        DailyLineItem.at_time.asc(),
        DailyLineItem.id.asc(),
    ).all()


def sum_line_items_by_kind(
    db: Session, store_id: int, report_date: date, kind: str,
) -> float:
    """Σ amount for a single kind on one day. The DailyReport row's
    discriminated total fields (cash_purchases, cash_expense, etc.)
    are derived from these on save — this helper is the single
    source for that derivation."""
    total = (
        db.query(func.coalesce(func.sum(DailyLineItem.amount), 0.0))
          .filter(
              DailyLineItem.store_id == store_id,
              DailyLineItem.report_date == report_date,
              DailyLineItem.kind == kind,
          )
          .scalar()
    )
    return float(total or 0.0)
