"""DailyBook module — Controllers (FastAPI router).

Mounts at ``/api/v2/daily/*``. Owns the JSON surface for the
daily cash-ledger and its line-items — the React SPA at
``/app/daily/*`` consumes these endpoints.
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
    LineItemUpdateRequest,
    MTBreakdownResponse,
    MTBreakdownRowResponse,
    MTBreakdownWriteRequest,
    PeriodSummaryResponse,
    TransferCompanyTotalsResponse,
    TransfersSummaryResponse,
)
from api.Modules.DailyBook.Services import (
    DailyReportLockedError,
    DailyReportSummary,
    LINE_ITEM_KINDS,
    LineItemValidationError,
    MTWriteRow,
    add_line_item,
    delete_line_item,
    field_for_kind,
    is_known_kind,
    lock_report,
    parse_amount,
    parse_at_time,
    read_mt_breakdown,
    recompute_line_items_total,
    replace_mt_breakdown,
    summarize_period,
    summarize_report,
    summarize_transfers_for_day,
    unlock_report,
    update_daily_report,
    update_line_item,
)
from typing import Any


router = APIRouter()


def _to_row(s: DailyReportSummary) -> DailyReportRow:
    return DailyReportRow(
        id=s.id, store_id=s.store_id, report_date=s.report_date,
        taxable_sales=s.taxable_sales,
        non_taxable=s.non_taxable, sales_tax=s.sales_tax,
        bill_payment_charge=s.bill_payment_charge,
        phone_recargas=s.phone_recargas, boost_mobile=s.boost_mobile,
        money_transfer=s.money_transfer, money_order=s.money_order,
        check_cashing_fees=s.check_cashing_fees,
        return_check_hold_fees=s.return_check_hold_fees,
        forward_balance=s.forward_balance, from_bank=s.from_bank,
        rebates_commissions=s.rebates_commissions,
        return_check_paid_back=s.return_check_paid_back,
        other_cash_in=s.other_cash_in,
        cash_deposit=s.cash_deposit, safe_balance=s.safe_balance,
        payroll_expense=s.payroll_expense,
        cash_purchases=s.cash_purchases, cash_expense=s.cash_expense,
        check_purchases=s.check_purchases, check_expense=s.check_expense,
        outside_cash_drops=s.outside_cash_drops,
        checks_deposit=s.checks_deposit,
        other_cash_out=s.other_cash_out,
        over_short=s.over_short,
        locked=s.locked, notes=s.notes, locked_at=s.locked_at,
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
    claims: dict[str, Any] = Depends(get_principal),
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
    if fields or notes:
        # Summary lists the keys the operator touched (not the
        # values — over_short and total_disbursements are sensitive
        # so we audit the intent, not the numbers).  `notes`
        # appears as a separate flag because it doesn't ride
        # `fields`.
        changed = list(fields.keys())
        if notes:
            changed.append("notes")
        _audit_daily_action(
            db, claims, "update_daily_report",
            target_type="daily_report",
            target_id=f"{store_id}:{d.isoformat()}",
            target_label=f"Daily {d.isoformat()}",
            summary=f"changed: {', '.join(sorted(changed))}",
        )
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
    _audit_daily_action(
        db, claims, action,
        target_type="daily_report",
        target_id=str(report.id),
        target_label=(
            f"Daily {report.report_date.isoformat()}"
            if getattr(report, "report_date", None) else ""
        ),
        summary="",
    )


def _audit_daily_action(
    db, claims, action: str,
    *,
    target_type: str,
    target_id: str,
    target_label: str,
    summary: str,
) -> None:
    """Generic operator-audit emitter for daily-book mutations.

    CLAUDE.md invariant #7 — every mutating endpoint records an
    audit row.  This helper covers the field edit (`update_daily`),
    the cash-ledger line-item CRUD, and the per-company MT
    breakdown replace, all of which were silently mutating state
    before this helper landed (the lock/unlock pair was the only
    pre-existing audit emitter on the daily-book surface)."""
    from api.Modules.Audit.Services import record_operator_action
    record_operator_action(
        db,
        store_id=int(claims["store_id"]),
        user_id=int(claims["sub"]),
        user_name=claims.get("name") or claims.get("username") or "",
        user_role=claims.get("role") or "",
        target_type=target_type,
        target_id=target_id,
        target_label=target_label,
        action=action,
        summary=summary,
    )


@router.post(
    "/{store_id}/{report_date}/lock",
    response_model=DailyReportResponse,
)
def lock_daily_route(
    store_id: int = Path(..., ge=1),
    report_date: str = Path(...),
    db: Session = Depends(get_db),
    claims: dict[str, Any] = Depends(get_principal),
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
    from api.Modules.DailyBook.Models import DailyReport
    existing = (
        db.query(DailyReport)
          .filter_by(store_id=int(store_id), report_date=d)
          .first()
    )
    was_locked = bool(existing and existing.locked_at)
    user_id = int(claims["sub"])
    rpt = lock_report(db, int(store_id), d, locked_by_user_id=user_id)
    just_locked = not was_locked
    if just_locked:
        _audit_daily_lock_action(db, claims, "lock", rpt)
    db.commit()

    # Owner digest — fired only on a was-not-locked → locked
    # state transition so re-clicking the lock button doesn't spam
    # the inbox. Delivery failures are caught + logged inside the
    # Service; we never roll back the lock on email errors.
    #
    # Deferred to the job queue (D5) so the SMTP fan-out (N
    # recipients × ~500ms each) doesn't block the lock route's
    # response. In sync mode (the default), ``enqueue`` is a
    # direct call — same behavior as before. In queued mode the
    # worker picks up the job and the route returns immediately.
    if just_locked:
        try:
            from api.Core.Jobs import enqueue
            from api.Modules.Notifications.Services.locked_day_digest import (
                send_locked_day_digest,
            )
            enqueue(send_locked_day_digest, rpt.id)
        except Exception:
            import logging
            logging.getLogger(__name__).exception(
                "locked-day digest fan-out failed for report_id=%s",
                rpt.id,
            )

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
    claims: dict[str, Any] = Depends(get_principal),
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
    from api.Modules.DailyBook.Models import DailyReport
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


def _require_store_match(claims: dict[str, Any], store_id: int) -> None:
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
    claims: dict[str, Any] = Depends(get_principal),
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
    claims: dict[str, Any] = Depends(get_principal),
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
        at = parse_at_time(body.at_time) if body.at_time.strip() else None
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
    # Each cash-ledger entry the cashier logs (cash in, cash out,
    # drop, bank deposit, …) is financially material — "who logged
    # this $500 drop at 2pm?" should be answerable from the audit
    # feed, not just the line-item row's `created_by` field.
    _audit_daily_action(
        db, claims, "create_line_item",
        target_type="daily_line_item",
        target_id=str(row.id),
        target_label=f"{body.kind} on {d.isoformat()}",
        summary=(
            f"kind={body.kind} amount=${float(amt):,.2f} "
            f"at={at.isoformat() if at else ''}"
        ),
    )
    db.commit()
    return _line_item_row(row)


@router.patch(
    "/{store_id}/line-items/{item_id}",
    response_model=LineItemRow,
)
def line_items_update_route(
    store_id: int = Path(..., ge=1),
    item_id: int = Path(..., ge=1),
    body: LineItemUpdateRequest = ...,
    db: Session = Depends(get_db),
    claims: dict[str, Any] = Depends(get_principal),
) -> LineItemRow:
    """Patch one line item in place.  Same scope + lock + return-
    check-link rules as create / delete:
      - Cross-store edits return 403.
      - Locked daily reports return 403 with "unlock first".
      - Rows linked to a ReturnCheck return 409 ("edit it from
        Books → Return Checks").

    The DailyReport's roll-up total is recomputed after a
    successful patch so the parent field stays accurate.  Every
    patch writes an operator-audit row.
    """
    _require_store_match(claims, store_id)
    item = (
        db.query(DailyLineItem)
          .filter_by(id=item_id, store_id=int(store_id))
          .first()
    )
    if item is None:
        # Same opaque 404 for missing IDs and cross-tenant probes.
        raise HTTPException(status_code=404, detail="Line item not found")

    # Lock check — the parent daily report's lock blanket-rejects
    # every mutation, including line-item edits.  Match the
    # update_daily_report path's 403 + "unlock first" UX.
    from api.Modules.DailyBook.Services.locks import is_locked
    if is_locked(db, int(store_id), item.report_date):
        raise HTTPException(
            status_code=403,
            detail="Daily report is locked — unlock it before editing.",
        )

    fields = body.model_dump(exclude_unset=True)
    parsed_time = None
    if "at_time" in fields and fields["at_time"] is not None:
        try:
            parsed_time = parse_at_time(fields["at_time"])
        except LineItemValidationError as exc:
            raise HTTPException(status_code=422, detail=str(exc))
    amount = fields.get("amount")
    if amount is not None and amount <= 0:
        raise HTTPException(
            status_code=422,
            detail="Amount must be greater than zero.",
        )

    original_amount = float(item.amount or 0)
    try:
        update_line_item(
            db, item,
            at_time=parsed_time,
            amount=amount,
            note=fields.get("note"),
        )
    except LineItemValidationError as exc:
        raise HTTPException(status_code=409, detail=str(exc))

    # Recompute parent roll-up so the DailyReport stays in sync.
    target_field = field_for_kind(item.kind)
    if target_field:
        recompute_line_items_total(
            db, int(store_id), item.report_date,
            kind=item.kind, daily_report_field=target_field,
        )

    # Audit row — same shape as delete (kind + amount delta).
    new_amount = float(item.amount or 0)
    _audit_daily_action(
        db, claims, "update_line_item",
        target_type="daily_line_item",
        target_id=str(item_id),
        target_label=f"{item.kind} on {item.report_date.isoformat()}",
        summary=(
            f"kind={item.kind} amount=${original_amount:,.2f}"
            f"→${new_amount:,.2f}"
        ),
    )
    db.commit()

    return LineItemRow(
        id=item.id,
        kind=item.kind,
        at_time=item.at_time.strftime("%H:%M") if item.at_time else "",
        amount=float(item.amount or 0),
        note=item.note or "",
        return_check_id=item.return_check_id,
    )


@router.delete(
    "/{store_id}/line-items/{item_id}",
    status_code=204,
)
def line_items_delete_route(
    store_id: int = Path(..., ge=1),
    item_id: int = Path(..., ge=1),
    db: Session = Depends(get_db),
    claims: dict[str, Any] = Depends(get_principal),
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
    deleted_amount = float(getattr(item, "amount", 0) or 0)
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
    # Deletions are the cash-ledger entries most worth auditing —
    # "where did that $500 drop go?" should land on a deletion
    # row, not silence.
    _audit_daily_action(
        db, claims, "delete_line_item",
        target_type="daily_line_item",
        target_id=str(item_id),
        target_label=f"{kind} on {report_date.isoformat()}",
        summary=f"kind={kind} amount=${deleted_amount:,.2f}",
    )
    db.commit()


# ── Money-transfer auto-fill ──────────────────────────────────


@router.get(
    "/{store_id}/{report_date}/transfers-summary",
    response_model=TransfersSummaryResponse,
)
def transfers_summary_route(
    store_id: int = Path(..., ge=1),
    report_date: str = Path(...),
    db: Session = Depends(get_db),
    claims: dict[str, Any] = Depends(get_principal),
) -> TransfersSummaryResponse:
    """Auto-fill summary for the Daily Book's Money Transfers tab.

    Aggregates active (non-cancelled) `transfer` rows for the day
    by company. Cashiers see this as a read-only "Auto" table on
    the Money Transfers panel; the grand total is what the daily
    book's `money_transfer` receipt line should reflect when the
    operator hasn't manually overridden it.

    Cross-store + superadmin → 403 with the same opaque message as
    the rest of the daily-book write surface.
    """
    _require_store_match(claims, store_id)
    d = _parse_date(report_date, field="report_date")
    summary = summarize_transfers_for_day(db, int(store_id), d)
    return TransfersSummaryResponse(
        companies=summary.companies,
        by_company=[
            TransferCompanyTotalsResponse(
                company=row.company,
                count=row.count,
                amount=row.amount,
                fees=row.fees,
                federal_tax=row.federal_tax,
                commission=row.commission,
                total=row.total,
            )
            for row in summary.by_company
        ],
        grand_total=summary.grand_total,
    )


# ── Editable per-company MT breakdown ────────────────────────


@router.get(
    "/{store_id}/{report_date}/mt-breakdown",
    response_model=MTBreakdownResponse,
)
def mt_breakdown_get_route(
    store_id: int = Path(..., ge=1),
    report_date: str = Path(...),
    db: Session = Depends(get_db),
    claims: dict[str, Any] = Depends(get_principal),
) -> MTBreakdownResponse:
    """Read the per-company Money Transfer breakdown for a day.

    Each row carries both `saved_*` values (from
    `MoneyTransferSummary` — the operator's last entry, if any)
    and `auto_*` values (from the employee transfer log). The
    React editor pre-fills inputs from saved-when-present and
    auto-otherwise, so a fresh day picks up the log automatically
    and overridden days keep the operator's edits.
    """
    _require_store_match(claims, store_id)
    d = _parse_date(report_date, field="report_date")
    breakdown = read_mt_breakdown(db, int(store_id), d)
    return MTBreakdownResponse(
        rows=[
            MTBreakdownRowResponse(
                company=row.company,
                saved_amount=row.saved_amount,
                saved_fees=row.saved_fees,
                saved_federal_tax=row.saved_federal_tax,
                saved_commission=row.saved_commission,
                saved_total=row.saved_total,
                auto_amount=row.auto_amount,
                auto_fees=row.auto_fees,
                auto_federal_tax=row.auto_federal_tax,
                auto_commission=row.auto_commission,
                auto_count=row.auto_count,
                auto_total=row.auto_total,
            )
            for row in breakdown.rows
        ],
        saved_total=breakdown.saved_total,
        auto_total=breakdown.auto_total,
    )


@router.put(
    "/{store_id}/{report_date}/mt-breakdown",
    response_model=MTBreakdownResponse,
)
def mt_breakdown_put_route(
    store_id: int = Path(..., ge=1),
    report_date: str = Path(...),
    body: MTBreakdownWriteRequest = ...,
    db: Session = Depends(get_db),
    claims: dict[str, Any] = Depends(get_principal),
) -> MTBreakdownResponse:
    """Bulk-replace the per-company breakdown for one day.

    Every row in `body.rows` becomes a `MoneyTransferSummary`
    insert (zero-only rows are skipped to keep the table from
    bloating with empty companies). After the replace, the daily
    report's `money_transfer` field is updated to the new grand
    total so the receipts tab + total_receipts stay consistent in
    one transaction.

    Locked-day returns 403 — same UX as the rest of the daily-book
    write surface.
    """
    _require_store_match(claims, store_id)
    d = _parse_date(report_date, field="report_date")
    try:
        replace_mt_breakdown(
            db,
            store_id=int(store_id),
            report_date=d,
            rows=[
                MTWriteRow(
                    company=r.company,
                    amount=r.amount,
                    fees=r.fees,
                    federal_tax=r.federal_tax,
                    commission=r.commission,
                )
                for r in body.rows
            ],
        )
    except DailyReportLockedError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    # Money-transfer breakdown is the receipts attribution table —
    # changing it changes the daily P&L's company allocation.
    # Summary lists the companies whose rows were submitted (zero-
    # amount rows are filtered by the Service so they don't bloat
    # the audit row either).
    company_list = sorted({
        (r.company or "").strip() for r in body.rows
        if (r.amount or 0) or (r.fees or 0)
           or (r.federal_tax or 0) or (r.commission or 0)
    })
    _audit_daily_action(
        db, claims, "replace_mt_breakdown",
        target_type="mt_breakdown",
        target_id=f"{store_id}:{d.isoformat()}",
        target_label=f"MT breakdown {d.isoformat()}",
        summary=(
            f"companies={','.join(company_list)}" if company_list else "cleared"
        ),
    )
    db.commit()

    # Re-read so the response carries the fresh saved + auto view.
    breakdown = read_mt_breakdown(db, int(store_id), d)
    return MTBreakdownResponse(
        rows=[
            MTBreakdownRowResponse(
                company=row.company,
                saved_amount=row.saved_amount,
                saved_fees=row.saved_fees,
                saved_federal_tax=row.saved_federal_tax,
                saved_commission=row.saved_commission,
                saved_total=row.saved_total,
                auto_amount=row.auto_amount,
                auto_fees=row.auto_fees,
                auto_federal_tax=row.auto_federal_tax,
                auto_commission=row.auto_commission,
                auto_count=row.auto_count,
                auto_total=row.auto_total,
            )
            for row in breakdown.rows
        ],
        saved_total=breakdown.saved_total,
        auto_total=breakdown.auto_total,
    )
