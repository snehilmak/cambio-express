"""Bank-transaction service: list + summary metadata.

Composes the Repository's `list_transactions` with two summary
numbers the legacy `/bank/transactions` page header displays:

  uncategorized_count — across the WHOLE filtered window, not just
                         the visible page; drives the "X items need
                         a category" indicator.
  page_total_cents    — Σ |amount_cents| over the visible rows
                         (the per-page footer total).

PR 16 wires this into the FastAPI Controller; PR 17 flips the Flask
route to call this same Service.
"""
from dataclasses import dataclass
from typing import Iterable

from sqlalchemy.orm import Session

from api.Modules.BankSync.Models import BankTransaction
from api.Modules.BankSync.Repositories import (
    BankTransactionFilters,
    list_transactions,
)


@dataclass
class TransactionListPage:
    rows: list[BankTransaction]
    total: int
    page: int
    per_page: int
    total_pages: int
    page_total_cents: int
    uncategorized_count: int


def list_transactions_page(
    db: Session, store_ids: Iterable[int],
    filters: BankTransactionFilters,
    *, page: int = 1, per_page: int = 100,
) -> TransactionListPage:
    """Bundles the rows + paging meta + the two summary counts."""
    rows, total = list_transactions(
        db, store_ids, filters, page=page, per_page=per_page,
    )
    total_pages = max(1, (total + per_page - 1) // per_page) if total else 1
    page = max(1, min(page, total_pages))

    page_total_cents = sum(abs(r.amount_cents or 0) for r in rows)

    # Uncategorized count reflects the filter window with the
    # category-related filters cleared so the pill stays accurate
    # while the user toggles between categories. Date / account /
    # sign / search filters still apply — the count is "uncategorized
    # rows the user could currently be looking at".
    from dataclasses import replace
    uncat_filters = replace(
        filters, category_slug="", uncategorized_only=True,
    )
    _, uncategorized_count = list_transactions(
        db, store_ids, uncat_filters, page=1, per_page=1,
    )

    return TransactionListPage(
        rows=rows,
        total=total,
        page=page,
        per_page=per_page,
        total_pages=total_pages,
        page_total_cents=page_total_cents,
        uncategorized_count=uncategorized_count,
    )
