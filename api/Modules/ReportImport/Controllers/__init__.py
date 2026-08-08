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
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from api.Core.Audit import audit_operator
from api.Core.Database import get_db
from api.Modules.Auth.Controllers import get_principal
from api.Modules.Auth.Services.principal import require_permission
from api.Modules.DailyBook.Services.reports import DailyReportLockedError
from api.Modules.ReportImport.Requests import (
    IntermexCommitRequest,
    IntermexCommitResponse,
    IntermexParseRequest,
    IntermexReportResponse,
    IntermexTxnRowResponse,
    SectionTotalsResponse,
)
from api.Modules.ReportImport.Requests.reports import MAX_PDF_BYTES
from api.Modules.ReportImport.Services import (
    IntermexDailyReport,
    IntermexTxnRow,
    ReportCommitError,
    ReportParseError,
    SectionTotals,
    commit_intermex_to_mt_breakdown,
    parse_intermex_pdf,
)

router = APIRouter()


def _decode_pdf(content_base64: str) -> bytes:
    """Base64-decode + size-guard an uploaded PDF. 422 on any problem —
    the same clean-error contract the parse route relies on."""
    try:
        data = base64.b64decode(content_base64, validate=True)
    except (binascii.Error, ValueError):
        raise HTTPException(
            status_code=422, detail="Could not decode the uploaded file.",
        )
    if not data:
        raise HTTPException(status_code=422, detail="Empty file.")
    if len(data) > MAX_PDF_BYTES:
        raise HTTPException(
            status_code=422, detail="File is too large (max 15 MB).",
        )
    return data


def _parse_pdf_or_422(data: bytes) -> IntermexDailyReport:
    """Parse decoded PDF bytes into an ``IntermexDailyReport``, mapping
    every failure mode to a clean 422 (pdfplumber can raise assorted
    low-level errors on a corrupt / non-PDF payload)."""
    try:
        return parse_intermex_pdf(data)
    except ReportParseError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception:
        raise HTTPException(
            status_code=422,
            detail="Could not read this file as an Intermex PDF report.",
        )


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
    report = _parse_pdf_or_422(_decode_pdf(body.content_base64))
    return _to_response(report)


@router.post("/intermex/commit", response_model=IntermexCommitResponse)
def commit_intermex_route(
    body: IntermexCommitRequest,
    db: Session = Depends(get_db),
    claims: dict[str, Any] = Depends(get_principal),
) -> IntermexCommitResponse:
    """Commit a reviewed Intermex report into the day's money-transfer
    breakdown. The PDF is re-parsed server-side (the client never sends
    money numbers) and the active giros aggregate into the Intermex
    company row of ``report_date``'s MT breakdown — every other
    company's manual override is preserved. Returns a reconcile
    comparison against the transfers already logged for the day.

    Auth: a store operator with daily-book write access, scoped to
    their own store (cross-store commit → opaque 403, matching the
    daily-book write surface). A locked day → 403. A report with no
    settled giros, or one whose giros don't reconcile, → 422.
    """
    require_permission(claims, "daily_book", "update")
    claim_store = claims.get("store_id")
    if claim_store is None or int(claim_store) != int(body.store_id):
        raise HTTPException(
            status_code=403,
            detail=(
                "JWT does not authorize edits to this store's daily book."
            ),
        )
    try:
        d = datetime.strptime(body.report_date, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(
            status_code=422, detail="report_date must be YYYY-MM-DD",
        )

    report = _parse_pdf_or_422(_decode_pdf(body.content_base64))
    try:
        result = commit_intermex_to_mt_breakdown(
            db, store_id=int(body.store_id), report_date=d, report=report,
        )
    except ReportCommitError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except DailyReportLockedError as exc:
        raise HTTPException(status_code=403, detail=str(exc))

    audit_operator(
        db, claims,
        action="import_intermex_mt",
        target_type="mt_breakdown",
        target_id=f"{body.store_id}:{d.isoformat()}",
        target_label=f"MT breakdown {d.isoformat()}",
        summary=(
            f"intermex import: {result.giros_committed} giros, "
            f"amount={result.amount:.2f}"
        ),
    )
    db.commit()

    return IntermexCommitResponse(
        company=result.company,
        giros_committed=result.giros_committed,
        amount=result.amount, fees=result.fees,
        federal_tax=result.federal_tax,
        committed_total=result.committed_total,
        grand_total=result.grand_total,
        logged_amount=result.logged_amount,
        logged_total=result.logged_total,
        previous_saved_total=result.previous_saved_total,
        matches_logged=result.matches_logged,
    )
