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
from api.Modules.DailyBook.Models import DailyLineItem
from api.Modules.DailyBook.Repositories import list_line_items
from api.Modules.DailyBook.Requests import (
    DailyReportResponse,
    DailyReportRow,
    DailyReportUpdateRequest,
    LineItemCreateRequest,
    LineItemListResponse,
    LineItemRow,
    PeriodSummaryResponse,
)
from api.Modules.DailyBook.Services import (
    DailyReportLockedError,
    DailyReportSummary,
    LINE_ITEM_KINDS,
    LineItemValidationError,
    add_line_item,
    delete_line_item,
    field_for_kind,
    is_known_kind,
    lock_report,
    parse_amount,
    parse_at_time,
    recompute_line_items_total,
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


def _audit_daily_lock_action(db, claims, action, report):
    """Operator-audit helper for daily-report lock / unlock actions.
    Mirrors the legacy `record_op_audit('lock'/'unlock',
    'daily_report', ...)` calls that the Flask form-POST handlers
    used to make. With those handlers gone (PR #403), the audit row
    needs to land on this side or it silently disappears from the
    operator audit log."""
    from api.Modules.Audit.Services import record_operator_action
    record_operator_action(
        db,
        store_id=int(claims["store_id"]),
        user_id=int(claims["sub"]),
        user_name=claims.get("name") or claims.get("username") or "",
        user_role=claims.get("role") or "",
        target_type="daily_report",
        target_id=report.id,
        target_label=(
            f"Daily {report.report_date.isoformat()}"
            if getattr(report, "report_date", None) else ""
        ),
        action=action,
        summary="",
    )


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
    locked_at/locked_by. Cross-store / superadmin → 403.

    Writes an OperatorAuditLog row (`action='lock',
    target_type='daily_report'`) on a state transition (was-not-
    locked → locked). Already-locked re-lock attempts are no-ops
    and don't append a second audit row, matching the legacy
    contract."""
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
    # Snapshot the prior lock state — the audit row only fires on
    # a state transition (matches the legacy /daily/<ds>/lock
    # `was_locked` guard).
    from app import DailyReport
    existing = (
        db.query(DailyReport)
          .filter_by(store_id=int(store_id), report_date=d)
          .first()
    )
    was_locked = bool(existing and existing.locked_at)
    user_id = int(claims["sub"])
    rpt = lock_report(db, int(store_id), d, locked_by_user_id=user_id)
    if not was_locked:
        _audit_daily_lock_action(db, claims, "lock", rpt)
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
    at all (nothing to unlock).

    Writes an OperatorAuditLog row (`action='unlock'`) on a state
    transition (was-locked → not-locked). Already-unlocked report
    is a no-op + no second audit row."""
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
    from app import DailyReport
    existing = (
        db.query(DailyReport)
          .filter_by(store_id=int(store_id), report_date=d)
          .first()
    )
    was_locked = bool(existing and existing.locked_at)
    result = unlock_report(db, int(store_id), d)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail="No daily report logged for this date",
        )
    if was_locked:
        _audit_daily_lock_action(db, claims, "unlock", result)
    db.commit()
    summary = summarize_report(db, int(store_id), d)
    if summary is None:
        raise HTTPException(status_code=500, detail="Unlock failed")
    return DailyReportResponse(report=_to_row(summary))


# ── Line items ─────────────────────────────────────────────


def _line_item_row(item: DailyLineItem) -> LineItemRow:
    return LineItemRow(
        id=item.id,
        kind=item.kind,
        at_time=item.at_time.strftime("%H:%M") if item.at_time else "",
        amount=float(item.amount or 0),
        note=item.note or "",
        return_check_id=item.return_check_id,
    )


def _require_store_match(claims: dict, store_id: int) -> None:
    """Reject when the JWT's store_id claim doesn't match the URL.
    Cross-store + superadmin both → 403 with the same opaque
    message — never leak which case tripped."""
    claim_store = claims.get("store_id")
    if claim_store is None or int(claim_store) != int(store_id):
        raise HTTPException(
            status_code=403,
            detail=(
                "JWT does not authorize edits to this store's "
                "daily book."
            ),
        )


@router.get(
    "/{store_id}/{report_date}/line-items",
    response_model=LineItemListResponse,
)
def line_items_list_route(
    store_id: int = Path(..., ge=1),
    report_date: str = Path(...),
    kind: str = Query(
        "",
        description=(
            "Optional kind filter (cash_purchase, drop, etc.). "
            "Empty returns every kind for the day."
        ),
    ),
    db: Session = Depends(get_db),
    claims: dict = Depends(get_principal),
) -> LineItemListResponse:
    """Read-side endpoint for the daily book's line-item table.
    Auth + tenancy gate is the same as the rest of the daily-
    book write-side endpoints."""
    _require_store_match(claims, store_id)
    d = _parse_date(report_date, field="report_date")
    if kind and not is_known_kind(kind):
        raise HTTPException(
            status_code=422, detail=f"Unknown kind: {kind!r}",
        )
    rows = list_line_items(
        db, int(store_id), d,
        kinds=[kind] if kind else None,
    )
    return LineItemListResponse(items=[_line_item_row(r) for r in rows])


@router.post(
    "/{store_id}/{report_date}/line-items",
    response_model=LineItemRow,
    status_code=201,
)
def line_items_create_route(
    store_id: int = Path(..., ge=1),
    report_date: str = Path(...),
    body: LineItemCreateRequest = ...,
    db: Session = Depends(get_db),
    claims: dict = Depends(get_principal),
) -> LineItemRow:
    """Insert one line item under (store_id, report_date, kind).
    Server validates kind, time format, and positive amount via
    the same parsers the legacy form uses (`parse_at_time`,
    `parse_amount`) so error messages match for cutover parity.

    After the insert, the matching DailyReport field is
    re-derived from the kind's running total so the daily P&L
    stays consistent without an explicit re-save.
    """
    _require_store_match(claims, store_id)
    d = _parse_date(report_date, field="report_date")
    user_id = int(claims["sub"])

    if not is_known_kind(body.kind):
        raise HTTPException(
            status_code=422,
            detail=f"Unknown line-item kind: {body.kind!r}",
        )
    # Return-check paybacks come exclusively from the Return Checks
    # page (POST /return-checks/<id>/payment, which calls the
    # Service directly). Blocking the manual API path here keeps the
    # daily book in sync with that single source of truth and matches
    # the read-only UI the cashier sees in the SPA.
    if body.kind == "return_payback":
        raise HTTPException(
            status_code=403,
            detail=(
                "Log return-check paybacks via Books → Return Checks "
                "(Add Payment). The daily-book line auto-populates."
            ),
        )
    try:
        at = parse_at_time(body.at_time)
        amt = parse_amount(str(body.amount))
        row = add_line_item(
            db,
            store_id=int(store_id),
            report_date=d,
            kind=body.kind,
            at_time=at,
            amount=amt,
            note=body.note,
            created_by=user_id,
            allowed_kinds=LINE_ITEM_KINDS.keys(),
        )
        # Re-derive the DailyReport's matching field so the daily
        # P&L stays in sync without a separate save round-trip.
        target_field = field_for_kind(body.kind)
        if target_field:
            recompute_line_items_total(
                db, int(store_id), d,
                kind=body.kind, daily_report_field=target_field,
            )
    except LineItemValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    db.commit()
    return _line_item_row(row)


@router.delete(
    "/{store_id}/line-items/{item_id}",
    status_code=204,
)
def line_items_delete_route(
    store_id: int = Path(..., ge=1),
    item_id: int = Path(..., ge=1),
    db: Session = Depends(get_db),
    claims: dict = Depends(get_principal),
) -> None:
    """Delete one line item. The Service rejects deletes for rows
    linked to a ReturnCheck (see DailyLineItem.return_check_id) —
    those mirror Return-Checks-side state and must be removed
    from there. We also re-derive the DailyReport field after
    the delete so the daily P&L stays accurate."""
    _require_store_match(claims, store_id)
    item = (
        db.query(DailyLineItem)
          .filter_by(id=item_id, store_id=int(store_id))
          .first()
    )
    if item is None:
        # Same opaque 404 for missing IDs and cross-tenant probes.
        raise HTTPException(status_code=404, detail="Line item not found")

    report_date = item.report_date
    kind = item.kind
    try:
        delete_line_item(db, item)
    except LineItemValidationError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    target_field = field_for_kind(kind)
    if target_field:
        recompute_line_items_total(
            db, int(store_id), report_date,
            kind=kind, daily_report_field=target_field,
        )
    db.commit()
