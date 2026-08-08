"""ACH batch write Service.

Mirrors the legacy /batches/new and /batches/<id>/edit Flask
routes. Audit logging stays on the legacy `record_op_audit`
helper (imported at call time) so the SPA's writes show up in
the same audit trail the admin already trusts.
"""
from dataclasses import dataclass
from datetime import date

from sqlalchemy.orm import Session

from api.Modules.Batches.Models import ACHBatch


class BatchValidationError(ValueError):
    """User-facing validation failure (duplicate batch_ref, etc.)."""


class BatchNotFoundError(LookupError):
    pass


@dataclass
class BatchWriteInput:
    """Fields a batch create / edit accepts. The Controller
    layer parses + validates the HTTP request body into this
    shape so the Service stays HTTP-agnostic."""
    ach_date: date
    company: str
    batch_ref: str
    ach_amount: float
    transfer_dates: str = ""
    status: str = "Pending"
    reconciled: bool = False
    notes: str = ""


def _check_unique_ref(
    db: Session, store_id: int, batch_ref: str,
    exclude_id: int | None = None,
) -> None:
    """The model has UNIQUE (store_id, batch_ref). Catch the
    collision before INSERT so the operator gets a clear 422
    rather than a SQLAlchemy IntegrityError."""
    q = (
        db.query(ACHBatch)
          .filter_by(store_id=store_id, batch_ref=batch_ref)
    )
    if exclude_id is not None:
        q = q.filter(ACHBatch.id != exclude_id)
    if q.first() is not None:
        raise BatchValidationError(
            f"A batch with ref {batch_ref!r} already exists in this store.",
        )


def create_batch(
    db: Session, store_id: int, payload: BatchWriteInput,
) -> ACHBatch:
    """Insert a new ACHBatch row. Caller commits."""
    _check_unique_ref(db, store_id, payload.batch_ref)
    row = ACHBatch(
        store_id=store_id,
        ach_date=payload.ach_date,
        company=payload.company,
        batch_ref=payload.batch_ref,
        ach_amount=payload.ach_amount,
        transfer_dates=payload.transfer_dates,
        status=payload.status or "Pending",
        reconciled=bool(payload.reconciled),
        notes=payload.notes,
    )
    db.add(row)
    db.flush()
    return row


def update_batch(
    db: Session, *, batch_id: int, store_id: int,
    payload: BatchWriteInput,
) -> ACHBatch:
    """Update an existing batch in the caller's store. Cross-
    tenant lookups raise BatchNotFoundError. Caller commits."""
    row = (
        db.query(ACHBatch)
          .filter_by(id=batch_id, store_id=store_id)
          .first()
    )
    if row is None:
        raise BatchNotFoundError(f"Batch id={batch_id}")
    _check_unique_ref(
        db, store_id, payload.batch_ref, exclude_id=batch_id,
    )
    row.ach_date = payload.ach_date
    row.company = payload.company
    row.batch_ref = payload.batch_ref
    row.ach_amount = payload.ach_amount
    row.transfer_dates = payload.transfer_dates
    row.status = payload.status or "Pending"
    row.reconciled = bool(payload.reconciled)
    row.notes = payload.notes
    db.flush()
    return row


def find_batch(
    db: Session, store_id: int, batch_id: int,
) -> ACHBatch | None:
    return (
        db.query(ACHBatch)
          .filter_by(id=batch_id, store_id=store_id)
          .first()
    )
