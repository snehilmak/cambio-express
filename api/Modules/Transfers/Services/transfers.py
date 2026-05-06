"""Transfer ledger services.

Read-side: `list_transfers` composes the Repository's
`list_with_filters` + a "page totals" pass over the rows.

The page total exists because the legacy `/transfers` route renders
a header that sums the send + fee + tax for the rows on the current
page (NOT the whole filtered set). Lifting that calculation here
keeps the controller a thin shell.
"""
from dataclasses import dataclass
from typing import Iterable

from sqlalchemy.orm import Session

from api.Modules.Transfers.Models import Transfer
from api.Modules.Transfers.Repositories import (
    TransferFilters,
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
