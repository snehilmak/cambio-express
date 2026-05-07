"""ACH batch read-side service.

Wraps `list_batches_for_store` with the bulk transfer-total +
count lookups so each row arrives at the controller already
carrying its variance + count. Avoids the legacy
`ACHBatch.transfers_total` per-row N+1.
"""
from dataclasses import dataclass

from sqlalchemy.orm import Session

from api.Modules.Batches.Models import ACHBatch
from api.Modules.Batches.Repositories import (
    list_batches_for_store,
    sum_transfer_totals_for_batch_refs,
    transfer_count_by_batch_ref,
)


@dataclass
class BatchSummary:
    """Service-layer DTO for one ACH batch with precomputed
    totals. Controllers convert this into the wire schema."""
    batch: ACHBatch
    transfers_total: float
    transfer_count: int

    @property
    def variance(self) -> float:
        return round(
            (self.batch.ach_amount or 0) - self.transfers_total, 2,
        )


def list_store_batches(
    db: Session, store_id: int,
    *, sort: str = "", direction: str = "desc",
) -> list[BatchSummary]:
    """All batches for one store with totals + counts pre-bulked.
    Returns Service DTOs in the same order the Repository sort
    produced."""
    rows = list_batches_for_store(
        db, store_id, sort=sort, direction=direction,
    )
    refs = [r.batch_ref for r in rows if r.batch_ref]
    totals = sum_transfer_totals_for_batch_refs(db, store_id, refs)
    counts = transfer_count_by_batch_ref(db, store_id, refs)
    return [
        BatchSummary(
            batch=r,
            transfers_total=totals.get(r.batch_ref, 0.0),
            transfer_count=counts.get(r.batch_ref, 0),
        )
        for r in rows
    ]
