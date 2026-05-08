"""ReturnChecks module — Controllers (FastAPI router).

Mounts at `/api/v2/return-checks/*`. Endpoints:

  GET    /                  list (optional ?status= filter)
  GET    /{id}              single-row detail
  POST   /                  create new pending check
  PUT    /{id}              edit core fields
  POST   /{id}/mark-loss    pending → loss
  POST   /{id}/mark-fraud   pending → fraud
  POST   /{id}/reopen       loss/fraud/recovered → pending
  GET    /{id}/payments     list payments

Per-payment write endpoints (POST/DELETE on payments) ship in
a follow-up PR — they auto-create matching DailyLineItem rows
which deserves its own focused migration.
"""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from sqlalchemy.orm import Session

from api.Core.Database import get_db
from api.Modules.Auth.Controllers import get_principal
from api.Modules.ReturnChecks.Repositories import (
    find_return_check,
    list_payments,
    list_return_checks,
)
from api.Modules.ReturnChecks.Requests import (
    ReturnCheckListResponse,
    ReturnCheckPaymentRow,
    ReturnCheckPaymentsResponse,
    ReturnCheckResponse,
    ReturnCheckRow,
    ReturnCheckWriteRequest,
)
from api.Modules.ReturnChecks.Services import (
    ReturnCheckNotFoundError,
    ReturnCheckStateError,
    ReturnCheckWriteInput,
    create_return_check,
    mark_fraud,
    mark_loss,
    reopen,
    update_return_check,
)


router = APIRouter()


def _require_admin_scope(claims: dict) -> int:
    sid = claims.get("store_id")
    if sid is None:
        raise HTTPException(
            status_code=403,
            detail="JWT does not carry a store scope.",
        )
    if claims.get("role") not in ("admin", "owner", "superadmin"):
        raise HTTPException(
            status_code=403,
            detail="Only store admins can manage return checks.",
        )
    return int(sid)


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
    claims: dict = Depends(get_principal),
) -> ReturnCheckListResponse:
    sid = claims.get("store_id")
    if sid is None:
        raise HTTPException(
            status_code=403,
            detail="JWT does not carry a store scope.",
        )
    rows = list_return_checks(db, int(sid), status=status)
    return ReturnCheckListResponse(rows=[_row(r) for r in rows])


@router.get("/{rc_id}", response_model=ReturnCheckResponse)
def get_route(
    rc_id: int = Path(..., ge=1),
    db: Session = Depends(get_db),
    claims: dict = Depends(get_principal),
) -> ReturnCheckResponse:
    sid = claims.get("store_id")
    if sid is None:
        raise HTTPException(
            status_code=403,
            detail="JWT does not carry a store scope.",
        )
    rc = find_return_check(db, int(sid), rc_id)
    if rc is None:
        raise HTTPException(status_code=404, detail="Return check not found")
    return ReturnCheckResponse(return_check=_row(rc))


@router.post("", response_model=ReturnCheckResponse, status_code=201)
def create_route(
    body: ReturnCheckWriteRequest,
    db: Session = Depends(get_db),
    claims: dict = Depends(get_principal),
) -> ReturnCheckResponse:
    sid = _require_admin_scope(claims)
    payload = _parse_payload(body)
    user_id = int(claims["sub"])
    row = create_return_check(
        db, store_id=sid, created_by=user_id, payload=payload,
    )
    db.commit()
    return ReturnCheckResponse(return_check=_row(row))


@router.put("/{rc_id}", response_model=ReturnCheckResponse)
def update_route(
    rc_id: int = Path(..., ge=1),
    body: ReturnCheckWriteRequest = ...,
    db: Session = Depends(get_db),
    claims: dict = Depends(get_principal),
) -> ReturnCheckResponse:
    sid = _require_admin_scope(claims)
    payload = _parse_payload(body)
    try:
        row = update_return_check(
            db, store_id=sid, rc_id=rc_id, payload=payload,
        )
    except ReturnCheckNotFoundError:
        raise HTTPException(status_code=404, detail="Return check not found")
    db.commit()
    return ReturnCheckResponse(return_check=_row(row))


def _transition(
    db: Session, store_id: int, rc_id: int, transition_fn,
) -> ReturnCheckResponse:
    try:
        row = transition_fn(db, store_id, rc_id)
    except ReturnCheckNotFoundError:
        raise HTTPException(status_code=404, detail="Return check not found")
    except ReturnCheckStateError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    db.commit()
    return ReturnCheckResponse(return_check=_row(row))


@router.post(
    "/{rc_id}/mark-loss",
    response_model=ReturnCheckResponse,
)
def mark_loss_route(
    rc_id: int = Path(..., ge=1),
    db: Session = Depends(get_db),
    claims: dict = Depends(get_principal),
) -> ReturnCheckResponse:
    sid = _require_admin_scope(claims)
    return _transition(db, sid, rc_id, mark_loss)


@router.post(
    "/{rc_id}/mark-fraud",
    response_model=ReturnCheckResponse,
)
def mark_fraud_route(
    rc_id: int = Path(..., ge=1),
    db: Session = Depends(get_db),
    claims: dict = Depends(get_principal),
) -> ReturnCheckResponse:
    sid = _require_admin_scope(claims)
    return _transition(db, sid, rc_id, mark_fraud)


@router.post(
    "/{rc_id}/reopen",
    response_model=ReturnCheckResponse,
)
def reopen_route(
    rc_id: int = Path(..., ge=1),
    db: Session = Depends(get_db),
    claims: dict = Depends(get_principal),
) -> ReturnCheckResponse:
    sid = _require_admin_scope(claims)
    return _transition(db, sid, rc_id, reopen)


@router.get(
    "/{rc_id}/payments",
    response_model=ReturnCheckPaymentsResponse,
)
def payments_route(
    rc_id: int = Path(..., ge=1),
    db: Session = Depends(get_db),
    claims: dict = Depends(get_principal),
) -> ReturnCheckPaymentsResponse:
    sid = claims.get("store_id")
    if sid is None:
        raise HTTPException(
            status_code=403,
            detail="JWT does not carry a store scope.",
        )
    rc = find_return_check(db, int(sid), rc_id)
    if rc is None:
        raise HTTPException(status_code=404, detail="Return check not found")
    rows = list_payments(db, int(sid), rc_id)
    return ReturnCheckPaymentsResponse(
        payments=[
            ReturnCheckPaymentRow(
                id=p.id,
                return_check_id=p.return_check_id,
                amount=float(p.amount or 0),
                paid_on=p.paid_on.isoformat() if p.paid_on else "",
                method=p.payment_method or "",
                notes=p.note or "",
            )
            for p in rows
        ],
    )
