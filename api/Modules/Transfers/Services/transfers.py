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

from api.Modules.Transfers.Models import Transfer
from api.Modules.Transfers.Repositories import (
    TransferFilters,
    get_by_id_in_stores,
    list_with_filters,
)


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
    from app import TransferAudit
    transfer = get_by_id_in_stores(db, transfer_id, [store_id])
    if transfer is None:
        raise TransferNotFoundError(f"Transfer id={transfer_id}")
    db.query(TransferAudit).filter_by(
        store_id=store_id, transfer_id=transfer.id,
    ).delete(synchronize_session=False)
    db.delete(transfer)
    db.flush()
    return transfer
