"""DailyBook module — Controllers (FastAPI router).

Mounts at `/api/v2/daily/*`. Read-side endpoints:

  GET /daily/{store_id}/{report_date}     → single-day summary or 404.
  GET /daily/{store_id}/period            → ?from=&to=, period roll-up.

The legacy Flask `/daily/<id>` and monthly P&L pages still serve the
HTML chrome; this Controller is the JSON surface the React frontend
will call once cutover ships. Auth gating intentionally NOT here yet
(auth migration is module 5 of 6 in the ADR).
"""
from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from sqlalchemy.orm import Session

from api.Core.Database import get_db
from api.Modules.DailyBook.Requests import (
    DailyReportResponse,
    DailyReportRow,
    PeriodSummaryResponse,
)
from api.Modules.DailyBook.Services import (
    DailyReportSummary,
    summarize_period,
    summarize_report,
)


router = APIRouter()


def _to_row(s: DailyReportSummary) -> DailyReportRow:
    return DailyReportRow(
        id=s.id, store_id=s.store_id, report_date=s.report_date,
        taxable_sales=s.taxable_sales,
        non_taxable=s.non_taxable, sales_tax=s.sales_tax,
        money_transfer=s.money_transfer, money_order=s.money_order,
        cash_expense=s.cash_expense, check_expense=s.check_expense,
        cash_deposit=s.cash_deposit, checks_deposit=s.checks_deposit,
        safe_balance=s.safe_balance, over_short=s.over_short,
        locked=s.locked, notes=s.notes,
        total_receipts=s.total_receipts,
        total_disbursements=s.total_disbursements, net=s.net,
    )


def _parse_date(raw: str, *, field: str) -> date:
    try:
        return datetime.strptime(raw, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(
            status_code=422,
            detail=f"{field} must be YYYY-MM-DD",
        )


@router.get(
    "/{store_id}/period", response_model=PeriodSummaryResponse,
)
def period_route(
    store_id: int = Path(..., ge=1),
    from_: str = Query(..., alias="from"),
    to: str = Query(...),
    db: Session = Depends(get_db),
) -> PeriodSummaryResponse:
    d_from = _parse_date(from_, field="from")
    d_to = _parse_date(to, field="to")
    if d_from > d_to:
        d_from, d_to = d_to, d_from
    page = summarize_period(db, [store_id], d_from, d_to)
    return PeriodSummaryResponse(
        rows=[_to_row(r) for r in page.rows],
        total_receipts=page.total_receipts,
        total_disbursements=page.total_disbursements,
        net=page.net,
        days_logged=page.days_logged,
    )


@router.get(
    "/{store_id}/{report_date}",
    response_model=DailyReportResponse,
)
def daily_route(
    store_id: int = Path(..., ge=1),
    report_date: str = Path(...),
    db: Session = Depends(get_db),
) -> DailyReportResponse:
    d = _parse_date(report_date, field="report_date")
    summary = summarize_report(db, store_id, d)
    if summary is None:
        raise HTTPException(
            status_code=404,
            detail="No daily report logged for this date",
        )
    return DailyReportResponse(report=_to_row(summary))
