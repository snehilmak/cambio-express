"""MonthlyFinancial SQL helpers."""
from sqlalchemy.orm import Session

from api.Modules.Monthly.Models import MonthlyFinancial


def find_monthly_for(
    db: Session, store_id: int, year: int, month: int,
) -> MonthlyFinancial | None:
    """Return the MonthlyFinancial row for (store, year, month)
    or None when the operator hasn't logged that month yet."""
    return (
        db.query(MonthlyFinancial)
          .filter_by(store_id=store_id, year=year, month=month)
          .first()
    )


def list_logged_months(
    db: Session, store_id: int,
) -> list[tuple[int, int]]:
    """Every (year, month) pair that has a MonthlyFinancial row
    for this store. Sorted newest-first so the SPA's month
    picker can default to the most recent."""
    rows = (
        db.query(MonthlyFinancial.year, MonthlyFinancial.month)
          .filter_by(store_id=store_id)
          .order_by(
              MonthlyFinancial.year.desc(),
              MonthlyFinancial.month.desc(),
          )
          .all()
    )
    return [(int(r.year), int(r.month)) for r in rows]
