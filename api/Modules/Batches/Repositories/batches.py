"""ACHBatch SQL helpers.

Read-side queries the SPA's /app/batches page consumes via the
controller. We pre-compute the per-batch transfers_total + count
in two bulk queries so we don't N+1 across rows.
"""
from sqlalchemy import func
from sqlalchemy.orm import Session

from api.Modules.Batches.Models import ACHBatch, Transfer


# Sortable columns the controller exposes. Slugs match the
# legacy /batches route's `sort` query string for cutover parity.
SORT_COLUMNS = {
    "ach_date":   ACHBatch.ach_date,
    "company":    ACHBatch.company,
    "batch_ref":  ACHBatch.batch_ref,
    "ach_amount": ACHBatch.ach_amount,
    "status":     ACHBatch.status,
}


def list_batches_for_store(
    db: Session, store_id: int,
    *, sort: str = "", direction: str = "desc",
) -> list[ACHBatch]:
    """All ACH batches for a store, sorted. Empty `sort` falls
    back to the default (`ach_date desc`, then `id desc`)."""
    q = db.query(ACHBatch).filter(ACHBatch.store_id == store_id)
    col = SORT_COLUMNS.get(sort)
    if col is not None:
        q = q.order_by(
            col.asc() if direction == "asc" else col.desc(),
            ACHBatch.id.desc(),
        )
    else:
        q = q.order_by(
            ACHBatch.ach_date.desc(),
            ACHBatch.id.desc(),
        )
    return q.all()


def sum_transfer_totals_for_batch_refs(
    db: Session, store_id: int, batch_refs: list[str],
) -> dict[str, float]:
    """For a list of batch_ref strings, return a dict mapping
    each ref to Σ (send_amount + federal_tax) across the linked
    transfers.

    Note: the legacy ACHBatch.transfers_total property runs ONE
    query per batch — fine for a single row, expensive on a
    page of 50. This helper does it in one bulk query.
    """
    if not batch_refs:
        return {}
    rows = (
        db.query(
            Transfer.batch_id,
            (
                func.coalesce(func.sum(Transfer.send_amount), 0.0)
                + func.coalesce(func.sum(Transfer.federal_tax), 0.0)
            ).label("total"),
        )
        .filter(
            Transfer.store_id == store_id,
            Transfer.batch_id.in_(batch_refs),
        )
        .group_by(Transfer.batch_id)
        .all()
    )
    return {r.batch_id: float(r.total or 0) for r in rows}


def transfer_count_by_batch_ref(
    db: Session, store_id: int, batch_refs: list[str],
) -> dict[str, int]:
    """Bulk-count transfers per batch_ref."""
    if not batch_refs:
        return {}
    rows = (
        db.query(Transfer.batch_id, func.count(Transfer.id))
        .filter(
            Transfer.store_id == store_id,
            Transfer.batch_id.in_(batch_refs),
        )
        .group_by(Transfer.batch_id)
        .all()
    )
    return {ref: int(c) for ref, c in rows}
