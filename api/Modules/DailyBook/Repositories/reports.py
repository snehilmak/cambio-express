"""DailyReport SQL helpers.

DailyReport is keyed `(store_id, report_date)` — one row per
store per day. Lookup is almost always by either the unique
`(store, date)` pair or by `id` after a write.
"""
from datetime import date
from typing import Iterable

from sqlalchemy.orm import Session

from api.Modules.DailyBook.Models import DailyReport


def find_report_by_date(
    db: Session, store_id: int, report_date: date,
) -> DailyReport | None:
    """Lookup by `(store_id, report_date)` — the unique constraint
    guarantees at most one match. Returns `None` for stores that
    haven't logged a report on this date yet."""
    return (
        db.query(DailyReport)
          .filter(
              DailyReport.store_id == store_id,
              DailyReport.report_date == report_date,
          )
          .first()
    )


def find_prior_report(
    db: Session, store_id: int, before_date: date,
) -> DailyReport | None:
    """Most recent DailyReport for this store strictly before
    ``before_date``. Powers the forward-balance carry: today's
    opening cash is derived from the previous logged day's
    (outside_cash_drops + safe_balance). Returns ``None`` when the
    store has no earlier report — that's the "first day" case where
    the operator seeds the forward balance manually.

    "Previous logged day", not "yesterday": a store closed Sunday
    carries Saturday's close into Monday. Rows are only created when
    a day is actually saved / locked (a bare GET never creates one),
    so this skips gaps automatically."""
    return (
        db.query(DailyReport)
          .filter(
              DailyReport.store_id == store_id,
              DailyReport.report_date < before_date,
          )
          .order_by(DailyReport.report_date.desc())
          .first()
    )


def get_report_by_id(
    db: Session, report_id: int, store_ids: Iterable[int],
) -> DailyReport | None:
    """Scoped get-by-id. Returns `None` for cross-tenant lookups so
    callers translate to 404."""
    return (
        db.query(DailyReport)
          .filter(
              DailyReport.id == report_id,
              DailyReport.store_id.in_(store_ids),
          )
          .first()
    )


def list_reports_in_period(
    db: Session, store_ids: Iterable[int],
    d_from: date, d_to: date,
) -> list[DailyReport]:
    """All DailyReport rows for the given stores between d_from and
    d_to (inclusive), ordered by `report_date asc, id asc`. Used by
    the monthly P&L roll-up + the owner-umbrella summary."""
    return (
        db.query(DailyReport)
          .filter(
              DailyReport.store_id.in_(store_ids),
              DailyReport.report_date >= d_from,
              DailyReport.report_date <= d_to,
          )
          .order_by(
              DailyReport.report_date.asc(),
              DailyReport.id.asc(),
          )
          .all()
    )
