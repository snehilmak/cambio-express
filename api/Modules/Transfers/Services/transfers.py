"""Transfer ledger services.

Read-side: `list_transfers` composes the Repository's
`list_with_filters` + a "page totals" pass over the rows.

The page total exists because the legacy `/transfers` route renders
a header that sums the send + fee + tax for the rows on the current
page (NOT the whole filtered set). Lifting that calculation here
keeps the controller a thin shell.

Write-side (PR 33+): `delete_transfer` extracts the row-and-audit
cascade so the Flask delete route is a thin shell. Create / edit
remain on Flask until the federal-tax + customer-upsert business
logic moves into Services in subsequent PRs.
"""
from dataclasses import dataclass
from typing import Iterable

from sqlalchemy.orm import Session

from api.Modules.Customers.Services import upsert as upsert_customer
from api.Modules.Tenancy.Models import Store, User
from api.Modules.Transfers.Models import Transfer
from api.Modules.Transfers.Repositories import (
    TransferFilters,
    get_by_id_in_stores,
    list_with_filters,
)
# Sibling-module imports go through leaf modules (not the package
# ``__init__``) because the package re-exports symbols from THIS
# file. Importing through the package would create a partial-init
# cycle.
from api.Modules.Transfers.Services.audit import (
    TRANSFER_AUDIT_FIELDS,
    record_audit as record_transfer_audit,
    summarize_changes as summarize_transfer_changes,
    transfer_snapshot,
)
from api.Modules.Transfers.Services.form_inputs import pick_employee
from api.Modules.Transfers.Services.tax import federal_tax_for


@dataclass
class TransferListPage:
    """Service-layer return type for `list_transfers`. Bundles the
    rows + paging metadata + the page-totals the legacy template
    header displays."""
    rows: list[Transfer]
    total: int
    page: int
    per_page: int
    total_pages: int
    page_amount: float  # Σ (send_amount + fee + federal_tax) for the visible rows


class TransferNotFoundError(LookupError):
    """The transfer doesn't exist or belongs to a different store.
    Same exception type for both so callers can't enumerate "exists
    but cross-tenant" via the response shape."""


def list_transfers(
    db: Session, store_ids: Iterable[int], filters: TransferFilters,
    *, page: int = 1, per_page: int = 50,
) -> TransferListPage:
    """Page-of-transfers + meta. Mirrors the legacy `/transfers`
    route's data flow: filter, sort, paginate, compute page total."""
    rows, total = list_with_filters(
        db, store_ids, filters, page=page, per_page=per_page,
    )
    total_pages = max(1, (total + per_page - 1) // per_page) if total else 1
    page = max(1, min(page, total_pages))

    page_amount = float(sum(
        (r.send_amount or 0) + (r.fee or 0) + (r.federal_tax or 0)
        for r in rows
    ))
    return TransferListPage(
        rows=rows,
        total=total,
        page=page,
        per_page=per_page,
        total_pages=total_pages,
        page_amount=page_amount,
    )


@dataclass
class CreateTransferInput:
    """Validated transfer-create payload. Mirrors the fields the
    legacy `new_transfer` Flask route accepts; the Controller layer
    parses + validates the HTTP request body into this shape so the
    Service stays HTTP-agnostic.

    `federal_tax` is intentionally NOT here — it's always recomputed
    server-side from `(send_amount, service_type, country, store)`
    via `federal_tax_for`. Mirrors the legacy invariant — the form
    can't lie about the tax rate.
    """
    store_id: int
    created_by_user_id: int
    send_date: "object"        # datetime.date
    company: str
    service_type: str          # already passed through normalize_service_type
    sender_name: str
    send_amount: float
    fee: float = 0.0
    commission: float = 0.0
    recipient_name: str = ""
    country: str = ""
    recipient_phone: str = ""
    sender_phone: str = ""
    sender_phone_country: str = "+1"
    sender_address: str = ""
    sender_dob: "object" = None  # datetime.date | None
    confirm_number: str = ""
    status: str = "Sent"
    status_notes: str = ""
    batch_id: str = ""
    internal_notes: str = ""
    employee_id: int | None = None
    customer_id: int | None = None


def create_transfer(
    db: Session, payload: CreateTransferInput,
) -> Transfer:
    """Create a Transfer + its associated Customer upsert + audit
    log entry. Returns the persisted Transfer row.

    Composes the existing helpers:
      • Customers.upsert            — sender directory
      • federal_tax_for             — server-recomputed tax
      • pick_employee               — required "processed by" attribution
      • record_transfer_audit       — "created" log line

    Raises ValueError if the employee can't be resolved within the
    store. Caller is responsible for committing the outer transaction
    so the row is visible to subsequent reads.
    """
    user = db.query(User).filter_by(id=payload.created_by_user_id).first()
    if user is None:
        raise ValueError(f"Unknown created_by user_id={payload.created_by_user_id}")

    emp, emp_name = pick_employee(db, payload.store_id, payload.employee_id)
    if not emp:
        raise ValueError(
            "An employee from the store roster must be selected as "
            "Processed by before saving."
        )

    cust = upsert_customer(
        db, payload.store_id, payload.sender_name,
        payload.sender_phone_country, payload.sender_phone,
        address=payload.sender_address,
        dob=payload.sender_dob,
        customer_id=payload.customer_id,
    )

    store = db.query(Store).filter_by(id=payload.store_id).first()
    fed_tax = federal_tax_for(
        payload.send_amount, payload.service_type,
        store, country=payload.country,
    )

    transfer = Transfer(
        store_id=payload.store_id,
        created_by=user.id,
        customer_id=cust.id,
        send_date=payload.send_date,
        company=payload.company,
        service_type=payload.service_type,
        sender_name=payload.sender_name,
        send_amount=payload.send_amount,
        fee=payload.fee,
        federal_tax=fed_tax,
        commission=payload.commission,
        recipient_name=payload.recipient_name,
        country=payload.country,
        recipient_phone=payload.recipient_phone,
        sender_phone=payload.sender_phone,
        sender_phone_country=payload.sender_phone_country,
        sender_address=payload.sender_address,
        sender_dob=payload.sender_dob,
        confirm_number=payload.confirm_number,
        status=payload.status or "Sent",
        status_notes=payload.status_notes,
        batch_id=payload.batch_id,
        internal_notes=payload.internal_notes,
        employee_id=emp.id,
        employee_name=emp_name,
    )
    db.add(transfer)
    db.flush()
    record_transfer_audit(
        db, transfer, user, "created", emp.id, emp_name,
        f"Logged by {emp_name}.",
    )
    db.flush()
    return transfer


def update_transfer(
    db: Session, *, transfer_id: int, store_id: int,
    payload: CreateTransferInput,
) -> Transfer:
    """Update an existing transfer + audit + customer-upsert.

    Mirrors the write path of `create_transfer` but operates on an
    existing row rather than creating one. Reuses the same
    CreateTransferInput shape — every field is replaceable, no
    PATCH semantics. Cross-tenant lookups raise
    `TransferNotFoundError` (never 403, keeps tenancy opaque).

    The audit summary is built from a before/after diff via
    `transfer_snapshot` + `summarize_changes` so the audit log
    only mentions the fields that actually changed.
    """
    from datetime import datetime as _dt

    transfer = get_by_id_in_stores(db, transfer_id, [store_id])
    if transfer is None:
        raise TransferNotFoundError(f"Transfer id={transfer_id}")

    user = db.query(User).filter_by(id=payload.created_by_user_id).first()
    if user is None:
        raise ValueError(
            f"Unknown actor user_id={payload.created_by_user_id}"
        )

    emp, emp_name = pick_employee(db, store_id, payload.employee_id)
    if not emp:
        raise ValueError(
            "An employee from the store roster must be selected as "
            "Processed by before saving."
        )

    cust = upsert_customer(
        db, store_id, payload.sender_name,
        payload.sender_phone_country, payload.sender_phone,
        address=payload.sender_address,
        dob=payload.sender_dob,
        customer_id=payload.customer_id or transfer.customer_id,
    )

    store = db.query(Store).filter_by(id=store_id).first()

    before = transfer_snapshot(transfer)

    transfer.send_date              = payload.send_date
    transfer.company                = payload.company
    transfer.service_type           = payload.service_type
    transfer.sender_name            = payload.sender_name
    transfer.send_amount            = payload.send_amount
    transfer.fee                    = payload.fee
    transfer.commission             = payload.commission
    transfer.recipient_name         = payload.recipient_name
    transfer.country                = payload.country
    transfer.recipient_phone        = payload.recipient_phone
    transfer.sender_phone           = payload.sender_phone
    transfer.sender_phone_country   = payload.sender_phone_country
    transfer.sender_address         = payload.sender_address
    transfer.sender_dob             = payload.sender_dob
    transfer.confirm_number         = payload.confirm_number
    transfer.status                 = payload.status or "Sent"
    transfer.status_notes           = payload.status_notes
    transfer.batch_id               = payload.batch_id
    transfer.internal_notes         = payload.internal_notes
    transfer.employee_id            = emp.id
    transfer.employee_name          = emp_name
    transfer.customer_id            = cust.id
    # Always recompute server-side — same invariant as create.
    transfer.federal_tax            = federal_tax_for(
        transfer.send_amount, transfer.service_type, store,
        country=transfer.country,
    )
    transfer.updated_at             = _dt.utcnow()

    after = transfer_snapshot(transfer)
    summary = summarize_transfer_changes(before, after) or "No field changes."

    # Status-only edits are a distinct audit action so the admin
    # view can highlight them. Mirrors the legacy edit_transfer
    # route exactly.
    changed_fields = {
        f for f, _ in TRANSFER_AUDIT_FIELDS
        if (before.get(f) or None) != (after.get(f) or None)
    }
    action = "status_changed" if changed_fields == {"status"} else "updated"

    record_transfer_audit(
        db, transfer, user, action, emp.id, emp_name, summary,
    )
    db.flush()
    return transfer


def delete_transfer(
    db: Session, transfer_id: int, store_id: int,
) -> Transfer:
    """Delete a transfer + its audit-history cascade. Returns the
    Transfer row that was deleted (so callers can build an audit-log
    label before the row is fully gone). Raises TransferNotFoundError
    on cross-tenant or missing IDs.

    `TransferAudit` has an FK to `Transfer`, so we drop the audit
    rows for this transfer first. The transfer's audit history
    disappears with the record it described — that's the intent of
    deletion. Anything downstream that aggregates from transfers
    (batch totals, dashboard counts) is a live query and recomputes
    on the next page load.

    Caller is responsible for committing the surrounding transaction
    and for emitting the cross-route audit log entry (which is a
    Flask-side concern via `record_op_audit`).
    """
    # Lazy import — TransferAudit lives in app.py and isn't part of
    # the Transfers Models re-export today (audit migration is its
    # own PR).
    from api.Modules.Audit.Models import TransferAudit
    transfer = get_by_id_in_stores(db, transfer_id, [store_id])
    if transfer is None:
        raise TransferNotFoundError(f"Transfer id={transfer_id}")
    db.query(TransferAudit).filter_by(
        store_id=store_id, transfer_id=transfer.id,
    ).delete(synchronize_session=False)
    db.delete(transfer)
    db.flush()
    return transfer
