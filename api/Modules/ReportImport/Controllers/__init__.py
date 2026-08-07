"""ReportImport — Controllers (FastAPI router).

Mounts at ``/api/v2/report-import/*``.

``POST /intermex/parse`` — accept a base64 Intermex daily-close PDF,
parse it IN MEMORY, and return the structured rows for the operator to
review. Nothing is stored: the bytes live only for the duration of the
request. Committing the reviewed rows into the transfer log is a
separate (later) endpoint.
"""
import base64
import binascii
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from api.Modules.Auth.Controllers import get_principal
from api.Modules.Auth.Services.principal import require_permission
from api.Modules.ReportImport.Requests import (
    IntermexParseRequest,
    IntermexReportResponse,
    IntermexTxnRowResponse,
    SectionTotalsResponse,
)
from api.Modules.ReportImport.Requests.reports import MAX_PDF_BYTES
from api.Modules.ReportImport.Services import (
    IntermexDailyReport,
    IntermexTxnRow,
    ReportParseError,
    SectionTotals,
    parse_intermex_pdf,
)

router = APIRouter()


def _row(r: IntermexTxnRow) -> IntermexTxnRowResponse:
    return IntermexTxnRowResponse(
        section=r.section, confirm_number=r.confirm_number,
        send_amount=r.send_amount, fee=r.fee, federal_tax=r.federal_tax,
        total_collected=r.total_collected, cashier=r.cashier,
        cancelled=r.cancelled, replacement=r.replacement,
        reconciles=r.reconciles,
    )


def _totals(t: SectionTotals | None) -> SectionTotalsResponse | None:
    if t is None:
        return None
    return SectionTotalsResponse(
        count=t.count, processed=t.processed, voided=t.voided,
        amount=t.amount, fees=t.fees, balance=t.balance,
    )


def _to_response(report: IntermexDailyReport) -> IntermexReportResponse:
    return IntermexReportResponse(
        agency=report.agency,
        report_date=(report.report_date.isoformat()
                     if report.report_date else None),
        giros=[_row(r) for r in report.giros],
        money_orders=[_row(r) for r in report.money_orders],
        bill_payments=[_row(r) for r in report.bill_payments],
        giros_totals=_totals(report.giros_totals),
        money_order_totals=_totals(report.money_order_totals),
        bill_payment_totals=_totals(report.bill_payment_totals),
        all_reconcile=report.all_reconcile,
    )


@router.post("/intermex/parse", response_model=IntermexReportResponse)
def parse_intermex_route(
    body: IntermexParseRequest,
    claims: dict[str, Any] = Depends(get_principal),
) -> IntermexReportResponse:
    """Parse an uploaded Intermex daily-close PDF and return the
    structured rows for review. In-memory only — the PDF is never
    persisted.

    Auth: a store operator with daily-book write access (the import
    feeds the day's money-transfer log). Bad base64 / non-PDF / a
    layout the parser doesn't recognise all return 422 with a clear
    message rather than 500.
    """
    require_permission(claims, "daily_book", "update")
    try:
        data = base64.b64decode(body.content_base64, validate=True)
    except (binascii.Error, ValueError):
        raise HTTPException(
            status_code=422,
            detail="Could not decode the uploaded file.",
        )
    if not data:
        raise HTTPException(status_code=422, detail="Empty file.")
    if len(data) > MAX_PDF_BYTES:
        raise HTTPException(
            status_code=422,
            detail="File is too large (max 15 MB).",
        )
    try:
        report = parse_intermex_pdf(data)
    except ReportParseError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception:
        # pdfplumber can raise assorted low-level errors on a corrupt /
        # non-PDF payload — surface a clean 422 instead of a 500.
        raise HTTPException(
            status_code=422,
            detail="Could not read this file as an Intermex PDF report.",
        )
    return _to_response(report)
