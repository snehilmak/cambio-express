"""ReturnChecks module — Controllers (FastAPI router).

Mounts at `/api/v2/return-checks/*`. Endpoints:

  GET    /                       list (optional ?status= filter)
  GET    /{id}                   single-row detail
  POST   /                       create new pending check
  PUT    /{id}                   edit core fields
  POST   /{id}/mark-loss         pending → loss
  POST   /{id}/mark-fraud        pending → fraud
  POST   /{id}/reopen            loss/fraud/recovered → pending
  GET    /{id}/payments          list payments
  POST   /{id}/payments          record an installment + auto-post
                                 to the daily book; auto-flips
                                 status to 'recovered' when the
                                 full amount is reached
  DELETE /{id}/payments/{pid}    remove an installment + its
                                 shadow DailyLineItem; reverts
                                 'recovered' → 'pending' if the
                                 total drops below the full amount
"""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from sqlalchemy.orm import Session

from api.Core.Database import get_db
from api.Modules.Auth.Controllers import get_principal
from api.Modules.Auth.Services.principal import require_permission
from api.Modules.ReturnChecks.Repositories import (
    find_return_check,
    list_payments,
    list_return_checks,
)
from api.Modules.ReturnChecks.Requests import (
    ReturnCheckListResponse,
    ReturnCheckPaymentResponse,
    ReturnCheckPaymentRow,
    ReturnCheckPaymentWriteRequest,
    ReturnCheckPaymentsResponse,
    ReturnCheckResponse,
    ReturnCheckRow,
    ReturnCheckWriteRequest,
)
from api.Modules.ReturnChecks.Services import (
    RecordPaymentInput,
    ReturnCheckNotFoundError,
    ReturnCheckPaymentNotFoundError,
    ReturnCheckStateError,
    ReturnCheckWriteInput,
    create_return_check,
    delete_payment,
    mark_fraud,
    mark_loss,
    record_payment,
    reopen,
    update_return_check,
)
from typing import Any


router = APIRouter()


def _require_admin_scope(claims: dict[str, Any]) -> int:
    sid = claims.get("store_id")
    if sid is None:
        raise HTTPException(
            status_code=403,
            detail="JWT does not carry a store scope.",
        )
    return int(sid)


def _audit_return_check_action(
    db: Session, *, claims: dict[str, Any], action: str,
    target_id: str, target_label: str, summary: str,
) -> None:
    """Operator-audit emitter for return-check mutations.

    CLAUDE.md invariant #7 — every mutating endpoint records an
    audit row.  Return checks are a financial-recovery surface
    (money the store is trying to claw back after a bounced check)
    so every state change deserves a paper trail.  Before this
    helper landed, the seven mutation routes silently mutated
    state without writing audit; the CLAUDE.md "employee action
    audit" claim of coverage was wrong for this module.

    target_type is "return_check" for the parent + its lifecycle
    transitions, "return_check_payment" for the installment
    record/delete pair — keeps the audit feed filterable per
    legacy contract."""
    from api.Modules.Audit.Services import record_operator_action
    record_operator_action(
        db,
        store_id=int(claims["store_id"]),
        user_id=int(claims["sub"]),
        user_name=claims.get("name") or claims.get("username") or "",
        user_role=claims.get("role") or "",
        target_type=(
            "return_check_payment"
            if action in ("record_payment", "delete_payment")
            else "return_check"
        ),
        target_id=target_id,
        target_label=target_label,
        action=action,
        summary=summary,
    )


def _row(rc) -> ReturnCheckRow:
    return ReturnCheckRow(
        id=rc.id,
        bounced_on=rc.bounced_on.isoformat() if rc.bounced_on else "",
        customer_name=rc.customer_name or "",
        check_number=rc.check_number or "",
        payer_bank=rc.payer_bank or "",
        amount=float(rc.amount or 0),
        status=rc.status or "pending",
        status_changed_on=(
            rc.status_changed_on.isoformat()
            if rc.status_changed_on else ""
        ),
        notes=rc.notes or "",
        recovered_total=float(rc.recovered_total or 0),
        payment_count=len(rc.payments) if rc.payments else 0,
    )


def _parse_payload(body: ReturnCheckWriteRequest) -> ReturnCheckWriteInput:
    try:
        bounced_on = datetime.strptime(
            body.bounced_on, "%Y-%m-%d",
        ).date()
    except ValueError:
        raise HTTPException(
            status_code=422,
            detail={
                "field": "bounced_on",
                "message": "Date must be YYYY-MM-DD.",
            },
        )
    return ReturnCheckWriteInput(
        bounced_on=bounced_on,
        customer_name=body.customer_name,
        check_number=body.check_number,
        payer_bank=body.payer_bank,
        amount=float(body.amount or 0),
        notes=body.notes,
    )


@router.get("", response_model=ReturnCheckListResponse)
def list_route(
    status: str = Query("", description="Optional filter: pending, recovered, loss, fraud"),
    db: Session = Depends(get_db),
    claims: dict[str, Any] = Depends(get_principal),
) -> ReturnCheckListResponse:
    sid = claims.get("store_id")
    if sid is None:
        raise HTTPException(
            status_code=403,
            detail="JWT does not carry a store scope.",
        )
    require_permission(claims, "return_checks", "read")
    rows = list_return_checks(db, int(sid), status=status)
    return ReturnCheckListResponse(rows=[_row(r) for r in rows])


@router.get("/{rc_id}", response_model=ReturnCheckResponse)
def get_route(
    rc_id: int = Path(..., ge=1),
    db: Session = Depends(get_db),
    claims: dict[str, Any] = Depends(get_principal),
) -> ReturnCheckResponse:
    sid = claims.get("store_id")
    if sid is None:
        raise HTTPException(
            status_code=403,
            detail="JWT does not carry a store scope.",
        )
    require_permission(claims, "return_checks", "read")
    rc = find_return_check(db, int(sid), rc_id)
    if rc is None:
        raise HTTPException(status_code=404, detail="Return check not found")
    return ReturnCheckResponse(return_check=_row(rc))


@router.post("", response_model=ReturnCheckResponse, status_code=201)
def create_route(
    body: ReturnCheckWriteRequest,
    db: Session = Depends(get_db),
    claims: dict[str, Any] = Depends(get_principal),
) -> ReturnCheckResponse:
    sid = _require_admin_scope(claims)
    require_permission(claims, "return_checks", "create")
    payload = _parse_payload(body)
    user_id = int(claims["sub"])
    row = create_return_check(
        db, store_id=sid, created_by=user_id, payload=payload,
    )
    _audit_return_check_action(
        db, claims=claims, action="create_return_check",
        target_id=str(row.id),
        target_label=(row.customer_name or "")[:160],
        summary=(
            f"check #{row.check_number or '?'} amount=${float(row.amount or 0):,.2f} "
            f"bounced_on={row.bounced_on.isoformat() if row.bounced_on else ''}"
        ),
    )
    db.commit()
    return ReturnCheckResponse(return_check=_row(row))


@router.put("/{rc_id}", response_model=ReturnCheckResponse)
def update_route(
    rc_id: int = Path(..., ge=1),
    body: ReturnCheckWriteRequest = ...,
    db: Session = Depends(get_db),
    claims: dict[str, Any] = Depends(get_principal),
) -> ReturnCheckResponse:
    sid = _require_admin_scope(claims)
    require_permission(claims, "return_checks", "update")
    payload = _parse_payload(body)
    try:
        row = update_return_check(
            db, store_id=sid, rc_id=rc_id, payload=payload,
        )
    except ReturnCheckNotFoundError:
        raise HTTPException(status_code=404, detail="Return check not found")
    _audit_return_check_action(
        db, claims=claims, action="update_return_check",
        target_id=str(row.id),
        target_label=(row.customer_name or "")[:160],
        summary=(
            f"check #{row.check_number or '?'} amount=${float(row.amount or 0):,.2f}"
        ),
    )
    db.commit()
    return ReturnCheckResponse(return_check=_row(row))


def _transition(
    db: Session, store_id: int, rc_id: int, transition_fn,
    *, claims: dict[str, Any], action: str,
) -> ReturnCheckResponse:
    """Apply a `pending → loss / fraud / recovered → pending` Service
    transition and emit a matching audit row.  ``action`` is the
    audit-log verb (`mark_loss` / `mark_fraud` / `reopen`); it's
    distinct from the transition_fn so the audit feed can show
    the operator's intent rather than the new state."""
    try:
        row = transition_fn(db, store_id, rc_id)
    except ReturnCheckNotFoundError:
        raise HTTPException(status_code=404, detail="Return check not found")
    except ReturnCheckStateError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    _audit_return_check_action(
        db, claims=claims, action=action,
        target_id=str(row.id),
        target_label=(row.customer_name or "")[:160],
        summary=f"status=>{row.status or ''}",
    )
    db.commit()
    return ReturnCheckResponse(return_check=_row(row))


@router.post(
    "/{rc_id}/mark-loss",
    response_model=ReturnCheckResponse,
)
def mark_loss_route(
    rc_id: int = Path(..., ge=1),
    db: Session = Depends(get_db),
    claims: dict[str, Any] = Depends(get_principal),
) -> ReturnCheckResponse:
    sid = _require_admin_scope(claims)
    require_permission(claims, "return_checks", "update")
    return _transition(
        db, sid, rc_id, mark_loss, claims=claims, action="mark_loss",
    )


@router.post(
    "/{rc_id}/mark-fraud",
    response_model=ReturnCheckResponse,
)
def mark_fraud_route(
    rc_id: int = Path(..., ge=1),
    db: Session = Depends(get_db),
    claims: dict[str, Any] = Depends(get_principal),
) -> ReturnCheckResponse:
    sid = _require_admin_scope(claims)
    require_permission(claims, "return_checks", "update")
    return _transition(
        db, sid, rc_id, mark_fraud, claims=claims, action="mark_fraud",
    )


@router.post(
    "/{rc_id}/reopen",
    response_model=ReturnCheckResponse,
)
def reopen_route(
    rc_id: int = Path(..., ge=1),
    db: Session = Depends(get_db),
    claims: dict[str, Any] = Depends(get_principal),
) -> ReturnCheckResponse:
    sid = _require_admin_scope(claims)
    require_permission(claims, "return_checks", "update")
    return _transition(
        db, sid, rc_id, reopen, claims=claims, action="reopen_return_check",
    )


def _payment_row(p) -> ReturnCheckPaymentRow:
    return ReturnCheckPaymentRow(
        id=p.id,
        return_check_id=p.return_check_id,
        amount=float(p.amount or 0),
        paid_on=p.paid_on.isoformat() if p.paid_on else "",
        method=p.payment_method or "",
        notes=p.note or "",
    )


@router.get(
    "/{rc_id}/payments",
    response_model=ReturnCheckPaymentsResponse,
)
def payments_route(
    rc_id: int = Path(..., ge=1),
    db: Session = Depends(get_db),
    claims: dict[str, Any] = Depends(get_principal),
) -> ReturnCheckPaymentsResponse:
    sid = claims.get("store_id")
    if sid is None:
        raise HTTPException(
            status_code=403,
            detail="JWT does not carry a store scope.",
        )
    require_permission(claims, "return_checks", "read")
    rc = find_return_check(db, int(sid), rc_id)
    if rc is None:
        raise HTTPException(status_code=404, detail="Return check not found")
    rows = list_payments(db, int(sid), rc_id)
    return ReturnCheckPaymentsResponse(
        payments=[_payment_row(p) for p in rows],
    )


@router.post(
    "/{rc_id}/payments",
    response_model=ReturnCheckPaymentResponse,
    status_code=201,
)
def record_payment_route(
    rc_id: int = Path(..., ge=1),
    body: ReturnCheckPaymentWriteRequest = ...,
    db: Session = Depends(get_db),
    claims: dict[str, Any] = Depends(get_principal),
) -> ReturnCheckPaymentResponse:
    """Record one installment payment against a pending or
    recovered return check. Auto-creates the matching
    ``DailyLineItem(kind='return_payback')`` and re-derives the
    daily-book total + parent status."""
    sid = _require_admin_scope(claims)
    require_permission(claims, "return_checks", "update")
    try:
        paid_on = datetime.strptime(body.paid_on, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(
            status_code=422,
            detail={
                "field": "paid_on",
                "message": "Date must be YYYY-MM-DD.",
            },
        )
    payload = RecordPaymentInput(
        paid_on=paid_on,
        amount=float(body.amount or 0),
        method=body.method,
        note=body.note,
    )
    try:
        payment = record_payment(
            db, store_id=sid, rc_id=rc_id,
            created_by=claims.get("sub"),
            payload=payload,
        )
    except ReturnCheckNotFoundError:
        raise HTTPException(status_code=404, detail="Return check not found")
    except ReturnCheckStateError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    # Payments are the single most-audited event on this surface —
    # each payment shifts money + can auto-flip the parent to
    # 'recovered'.  Summary carries the amount + paid_on date so a
    # reconciliation question ("did we credit this customer twice?")
    # is one feed lookup away.
    rc = find_return_check(db, sid, rc_id)
    _audit_return_check_action(
        db, claims=claims, action="record_payment",
        target_id=str(payment.id),
        target_label=(getattr(rc, "customer_name", "") or "")[:160],
        summary=(
            f"rc={rc_id} amount=${float(payment.amount or 0):,.2f} "
            f"paid_on={payment.paid_on.isoformat() if payment.paid_on else ''}"
        ),
    )
    db.commit()
    db.refresh(payment)
    return ReturnCheckPaymentResponse(
        payment=_payment_row(payment),
        return_check=_row(rc),
    )


@router.delete(
    "/{rc_id}/payments/{payment_id}",
    response_model=ReturnCheckPaymentResponse,
)
def delete_payment_route(
    rc_id: int = Path(..., ge=1),
    payment_id: int = Path(..., ge=1),
    db: Session = Depends(get_db),
    claims: dict[str, Any] = Depends(get_principal),
) -> ReturnCheckPaymentResponse:
    sid = _require_admin_scope(claims)
    require_permission(claims, "return_checks", "delete")
    # Snapshot the payment before the Service deletes it so the audit
    # row carries the amount that walked out the door — answers
    # "we deleted payment #PID — how much was that?".
    from api.Modules.ReturnChecks.Repositories import find_payment
    pre_delete = find_payment(db, sid, rc_id, payment_id)
    pre_amount = float(getattr(pre_delete, "amount", 0) or 0)
    pre_paid_on = getattr(pre_delete, "paid_on", None) if pre_delete else None
    try:
        delete_payment(
            db, store_id=sid, rc_id=rc_id, payment_id=payment_id,
        )
    except ReturnCheckNotFoundError:
        raise HTTPException(status_code=404, detail="Return check not found")
    except ReturnCheckPaymentNotFoundError:
        raise HTTPException(status_code=404, detail="Payment not found")
    rc = find_return_check(db, sid, rc_id)
    _audit_return_check_action(
        db, claims=claims, action="delete_payment",
        target_id=str(payment_id),
        target_label=(getattr(rc, "customer_name", "") or "")[:160],
        summary=(
            f"rc={rc_id} amount=${pre_amount:,.2f} "
            f"paid_on={pre_paid_on.isoformat() if pre_paid_on else ''}"
        ),
    )
    db.commit()
    return ReturnCheckPaymentResponse(
        payment=None,
        return_check=_row(rc),
    )
