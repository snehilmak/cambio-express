"""ReturnChecks — Services."""
from datetime import date, datetime
from dataclasses import dataclass

from sqlalchemy.orm import Session

from api.Modules.ReturnChecks.Models import ReturnCheck
from api.Modules.ReturnChecks.Repositories import find_return_check


class ReturnCheckNotFoundError(LookupError):
    pass


class ReturnCheckStateError(ValueError):
    """Raised on illegal state transitions (e.g. marking a recovered
    row as loss without first reopening it)."""


@dataclass
class ReturnCheckWriteInput:
    bounced_on: date
    customer_name: str
    check_number: str
    payer_bank: str
    amount: float
    notes: str = ""


def create_return_check(
    db: Session, *, store_id: int, created_by: int | None,
    payload: ReturnCheckWriteInput,
) -> ReturnCheck:
    """Insert a new ReturnCheck row in pending status. Caller commits."""
    row = ReturnCheck(
        store_id=store_id,
        bounced_on=payload.bounced_on,
        customer_name=payload.customer_name,
        check_number=payload.check_number,
        payer_bank=payload.payer_bank,
        amount=float(payload.amount or 0),
        status="pending",
        notes=payload.notes,
        created_by=created_by,
    )
    db.add(row)
    db.flush()
    return row


def update_return_check(
    db: Session, *, store_id: int, rc_id: int,
    payload: ReturnCheckWriteInput,
) -> ReturnCheck:
    """Edit the core fields. Status / status_changed_on stay
    out of this path — those flow through the dedicated transition
    helpers below. Cross-tenant lookups raise NotFound."""
    row = find_return_check(db, store_id, rc_id)
    if row is None:
        raise ReturnCheckNotFoundError(f"id={rc_id}")
    row.bounced_on = payload.bounced_on
    row.customer_name = payload.customer_name
    row.check_number = payload.check_number
    row.payer_bank = payload.payer_bank
    row.amount = float(payload.amount or 0)
    row.notes = payload.notes
    db.flush()
    return row


def _set_status(
    db: Session, store_id: int, rc_id: int,
    *, target_status: str, allowed_from: tuple[str, ...],
) -> ReturnCheck:
    row = find_return_check(db, store_id, rc_id)
    if row is None:
        raise ReturnCheckNotFoundError(f"id={rc_id}")
    if row.status not in allowed_from:
        raise ReturnCheckStateError(
            f"Cannot move from {row.status} to {target_status}.",
        )
    row.status = target_status
    row.status_changed_on = date.today()
    row.updated_at = datetime.utcnow()
    db.flush()
    return row


def mark_loss(db: Session, store_id: int, rc_id: int) -> ReturnCheck:
    """Move pending → loss. The full `amount` becomes the loss in
    the month identified by `status_changed_on`."""
    return _set_status(
        db, store_id, rc_id,
        target_status="loss",
        allowed_from=("pending",),
    )


def mark_fraud(db: Session, store_id: int, rc_id: int) -> ReturnCheck:
    """Move pending → fraud. Same accounting as loss; tracked
    distinctly for fraud reporting."""
    return _set_status(
        db, store_id, rc_id,
        target_status="fraud",
        allowed_from=("pending",),
    )


def reopen(db: Session, store_id: int, rc_id: int) -> ReturnCheck:
    """Reopen a closed (loss / fraud / recovered) row back to
    pending. Clears status_changed_on so the row no longer
    contributes to any month's P&L until re-closed."""
    row = find_return_check(db, store_id, rc_id)
    if row is None:
        raise ReturnCheckNotFoundError(f"id={rc_id}")
    if row.status not in ("loss", "fraud", "recovered"):
        raise ReturnCheckStateError(
            f"Cannot reopen from status {row.status}.",
        )
    row.status = "pending"
    row.status_changed_on = None
    row.updated_at = datetime.utcnow()
    db.flush()
    return row


__all__ = [
    "ReturnCheckNotFoundError",
    "ReturnCheckStateError",
    "ReturnCheckWriteInput",
    "create_return_check",
    "mark_fraud",
    "mark_loss",
    "reopen",
    "update_return_check",
]
