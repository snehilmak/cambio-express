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
from api.Modules.Auth.Controllers import get_principal
from api.Modules.DailyBook.Requests import (
    DailyReportResponse,
    DailyReportRow,
    DailyReportUpdateRequest,
    PeriodSummaryResponse,
)
from api.Modules.DailyBook.Services import (
    DailyReportLockedError,
    DailyReportSummary,
    lock_report,
    summarize_period,
    summarize_report,
    unlock_report,
    update_daily_report,
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


@router.put(
    "/{store_id}/{report_date}",
    response_model=DailyReportResponse,
)
def update_daily_route(
    store_id: int = Path(..., ge=1),
    report_date: str = Path(...),
    body: DailyReportUpdateRequest = ...,
    db: Session = Depends(get_db),
    claims: dict = Depends(get_principal),
) -> DailyReportResponse:
    """Save the editable totals for one daily report.

    JWT-authed. The principal's `store_id` claim must match the
    URL `store_id` — cross-store writes return 403 to keep
    tenancy boundaries opaque (the endpoint isn't an enumeration
    oracle for other stores' report dates).

    Locked reports return 403 with a clear "unlock first"
    message — same UX as the legacy template's locked-banner.

    Auto-creates the row when the date is new.

    Line-item-derived fields (drops, check deposits, MT
    company breakdowns) are NOT writable here — they're driven
    by their own tables and migrate in follow-up PRs.
    """
    d = _parse_date(report_date, field="report_date")

    claim_store = claims.get("store_id")
    if claim_store is None or int(claim_store) != int(store_id):
        # Same opaque 403 for "no store scope" and
        # "wrong store" — never leak which one tripped.
        raise HTTPException(
            status_code=403,
            detail=(
                "JWT does not authorize edits to this store's "
                "daily book."
            ),
        )

    # Drop the `notes` field; everything else is the float subset
    # that update_daily_report writes via setattr — only fields
    # the caller actually included land on the row.
    payload = body.model_dump(exclude_unset=True)
    notes = payload.pop("notes", "")
    fields = {k: float(v) for k, v in payload.items() if v is not None}

    try:
        update_daily_report(
            db,
            store_id=int(store_id),
            report_date=d,
            fields=fields,
            notes=notes,
        )
    except DailyReportLockedError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    db.commit()

    summary = summarize_report(db, int(store_id), d)
    if summary is None:
        # Should never happen — update_daily_report ensured the
        # row exists. Defensive: surface as 500 rather than
        # confusing the client with a phantom 404.
        raise HTTPException(
            status_code=500,
            detail="Daily report disappeared after save",
        )
    return DailyReportResponse(report=_to_row(summary))


@router.post(
    "/{store_id}/{report_date}/lock",
    response_model=DailyReportResponse,
)
def lock_daily_route(
    store_id: int = Path(..., ge=1),
    report_date: str = Path(...),
    db: Session = Depends(get_db),
    claims: dict = Depends(get_principal),
) -> DailyReportResponse:
    """Mark a daily report as locked. Auto-creates the row when
    missing so a cashier can lock an empty day on purpose.
    Idempotent — already-locked reports keep their original
    locked_at/locked_by. Cross-store / superadmin → 403."""
    d = _parse_date(report_date, field="report_date")
    claim_store = claims.get("store_id")
    if claim_store is None or int(claim_store) != int(store_id):
        raise HTTPException(
            status_code=403,
            detail=(
                "JWT does not authorize edits to this store's "
                "daily book."
            ),
        )
    user_id = int(claims["sub"])
    lock_report(db, int(store_id), d, locked_by_user_id=user_id)
    db.commit()
    summary = summarize_report(db, int(store_id), d)
    if summary is None:
        raise HTTPException(status_code=500, detail="Lock failed")
    return DailyReportResponse(report=_to_row(summary))


@router.post(
    "/{store_id}/{report_date}/unlock",
    response_model=DailyReportResponse,
)
def unlock_daily_route(
    store_id: int = Path(..., ge=1),
    report_date: str = Path(...),
    db: Session = Depends(get_db),
    claims: dict = Depends(get_principal),
) -> DailyReportResponse:
    """Clear the lock on a daily report. Cross-store /
    superadmin → 403. Returns 404 if the date never had a report
    at all (nothing to unlock)."""
    d = _parse_date(report_date, field="report_date")
    claim_store = claims.get("store_id")
    if claim_store is None or int(claim_store) != int(store_id):
        raise HTTPException(
            status_code=403,
            detail=(
                "JWT does not authorize edits to this store's "
                "daily book."
            ),
        )
    result = unlock_report(db, int(store_id), d)
    db.commit()
    if result is None:
        raise HTTPException(
            status_code=404,
            detail="No daily report logged for this date",
        )
    summary = summarize_report(db, int(store_id), d)
    if summary is None:
        raise HTTPException(status_code=500, detail="Unlock failed")
    return DailyReportResponse(report=_to_row(summary))
