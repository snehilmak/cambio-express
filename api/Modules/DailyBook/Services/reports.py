"""Daily-book summary services.

Read-side: turn raw DailyReport rows into the summary payloads the
React frontend (and the legacy template, once flipped) wants.

Two summaries:
  summarize_report — one DailyReport, with the derived
                     receipts/disbursements/net totals.
  summarize_period — list of reports + per-store + grand totals
                     across a date range.

Write-side (create/edit/lock/unlock + line-item CRUD) lands in PR 23+.
"""
from dataclasses import dataclass
from datetime import date
from typing import Iterable

from sqlalchemy.orm import Session

from api.Modules.DailyBook.Models import DailyReport
from api.Modules.DailyBook.Repositories import (
    find_report_by_date,
    list_reports_in_period,
)


@dataclass
class DailyReportSummary:
    """Wire-shape for one DailyReport. Receipts / disbursements /
    net are derived (Python-side) from the model's @property fields
    so the frontend doesn't have to recompute them."""
    id: int
    store_id: int
    report_date: str  # ISO YYYY-MM-DD
    taxable_sales: float
    non_taxable: float
    sales_tax: float
    money_transfer: float
    money_order: float
    cash_expense: float
    check_expense: float
    cash_deposit: float
    checks_deposit: float
    safe_balance: float
    over_short: float
    locked: bool
    notes: str
    total_receipts: float
    total_disbursements: float
    net: float


@dataclass
class PeriodSummary:
    """Roll-up for a date range. `rows` are individual reports; the
    summary fields are sums across them. Empty-period returns zeros
    + an empty list."""
    rows: list[DailyReportSummary]
    total_receipts: float
    total_disbursements: float
    net: float
    days_logged: int


def _summarize(r: DailyReport) -> DailyReportSummary:
    return DailyReportSummary(
        id=r.id,
        store_id=r.store_id,
        report_date=r.report_date.isoformat() if r.report_date else "",
        taxable_sales=float(r.taxable_sales or 0),
        non_taxable=float(r.non_taxable or 0),
        sales_tax=float(r.sales_tax or 0),
        money_transfer=float(r.money_transfer or 0),
        money_order=float(r.money_order or 0),
        cash_expense=float(r.cash_expense or 0),
        check_expense=float(r.check_expense or 0),
        cash_deposit=float(r.cash_deposit or 0),
        checks_deposit=float(r.checks_deposit or 0),
        safe_balance=float(r.safe_balance or 0),
        over_short=float(r.over_short or 0),
        locked=r.locked_at is not None,
        notes=r.notes or "",
        total_receipts=float(r.total_receipts or 0),
        total_disbursements=float(r.total_disbursements or 0),
        net=float((r.total_receipts or 0) - (r.total_disbursements or 0)),
    )


def summarize_report(
    db: Session, store_id: int, report_date: date,
) -> DailyReportSummary | None:
    """Single-report summary by `(store, date)`. Returns `None` for
    days the store hasn't logged yet."""
    r = find_report_by_date(db, store_id, report_date)
    if r is None:
        return None
    return _summarize(r)


def summarize_period(
    db: Session, store_ids: Iterable[int],
    d_from: date, d_to: date,
) -> PeriodSummary:
    """Date-range summary. Same row order as
    `list_reports_in_period`: report_date asc + id tie-break."""
    rows = list_reports_in_period(db, store_ids, d_from, d_to)
    summaries = [_summarize(r) for r in rows]
    total_receipts = sum(s.total_receipts for s in summaries)
    total_disbursements = sum(s.total_disbursements for s in summaries)
    return PeriodSummary(
        rows=summaries,
        total_receipts=total_receipts,
        total_disbursements=total_disbursements,
        net=total_receipts - total_disbursements,
        days_logged=len(summaries),
    )
