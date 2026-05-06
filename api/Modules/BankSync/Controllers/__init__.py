"""BankSync module — Controllers (FastAPI router).

Mounts at `/api/v2/bank/*`. PR 16 ships the read-side only:

  GET /bank/transactions → paginated list of BankTransaction rows.

PR 17 will flip the legacy /bank/transactions route to call the same
Service this Controller does. Write-side endpoints (rule CRUD,
manual categorization, daily-book post) come in subsequent PRs.

Auth gating intentionally NOT here yet (auth migration is module 5
of 6 in the ADR).
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from api.Core.Database import get_db
from api.Modules.BankSync.Models import StripeBankAccount
from api.Modules.BankSync.Repositories import BankTransactionFilters
from api.Modules.BankSync.Requests import (
    BankTransactionListResponse,
    BankTransactionRow,
)
from api.Modules.BankSync.Services import list_transactions_page


router = APIRouter()


def _parse_store_ids(store_ids: str) -> list[int]:
    try:
        ids = [int(s.strip()) for s in store_ids.split(",") if s.strip()]
    except ValueError as e:
        raise HTTPException(
            status_code=422,
            detail=f"store_ids must be comma-separated integers: {e}",
        )
    if not ids:
        raise HTTPException(
            status_code=422, detail="store_ids must include at least one ID",
        )
    return ids


def _account_labels(db: Session, ids: list[int]) -> dict[int, str]:
    """Bulk-fetch the StripeBankAccount.label for every account_id in
    `ids`. Centralised so the row adapter doesn't N+1."""
    if not ids:
        return {}
    rows = (
        db.query(StripeBankAccount)
          .filter(StripeBankAccount.id.in_(set(ids)))
          .all()
    )
    return {a.id: a.label for a in rows}


@router.get("/transactions", response_model=BankTransactionListResponse)
def list_transactions_route(
    store_ids: str = Query(...),
    posted_from: str = Query(""),
    posted_to: str = Query(""),
    account_id: str = Query(""),
    category_slug: str = Query(""),
    sign: str = Query("", pattern="^(|credit|debit)$"),
    q: str = Query(""),
    uncategorized_only: bool = Query(False),
    page: int = Query(1, ge=1),
    per_page: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
) -> BankTransactionListResponse:
    ids = _parse_store_ids(store_ids)
    filters = BankTransactionFilters.from_query({
        "posted_from": posted_from, "posted_to": posted_to,
        "account_id": account_id, "category_slug": category_slug,
        "sign": sign, "q": q,
        "uncategorized_only": "1" if uncategorized_only else "",
    })
    page_obj = list_transactions_page(
        db, ids, filters, page=page, per_page=per_page,
    )
    labels = _account_labels(
        db, [r.stripe_bank_account_id for r in page_obj.rows],
    )
    rows = [
        BankTransactionRow(
            id=r.id,
            posted_at=r.posted_at.isoformat() if r.posted_at else "",
            description=r.description or "",
            amount_cents=r.amount_cents,
            amount=r.amount,
            currency=r.currency or "usd",
            status=r.status or "posted",
            category_slug=r.category_slug or "",
            account_id=r.stripe_bank_account_id,
            account_label=labels.get(r.stripe_bank_account_id, ""),
        )
        for r in page_obj.rows
    ]
    return BankTransactionListResponse(
        rows=rows,
        total=page_obj.total,
        page=page_obj.page,
        per_page=page_obj.per_page,
        total_pages=page_obj.total_pages,
        page_total_cents=page_obj.page_total_cents,
        uncategorized_count=page_obj.uncategorized_count,
    )
