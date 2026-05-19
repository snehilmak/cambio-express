"""BankTransaction list + sum helpers.

`/bank/transactions` is a complex list endpoint with date range,
account, category, sign, and free-text filters. Migrating it
piece-by-piece — this PR ships the read repository helpers; the
Service layer composes them into the rendered list.
"""
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Iterable, Literal

from sqlalchemy import func
from sqlalchemy.orm import Session

from api.Modules.BankSync.Models import BankTransaction


@dataclass
class BankTransactionFilters:
    """Bag of filter values from the /bank/transactions query string."""
    posted_from: date | None = None
    posted_to: date | None = None
    account_id: int | None = None
    category_slug: str = ""
    # "" | "credit" | "debit" — credit = positive amount, debit = negative.
    sign: Literal["", "credit", "debit"] = ""
    q: str = ""  # ILIKE on description
    uncategorized_only: bool = False

    @classmethod
    def from_query(cls, args: Any) -> "BankTransactionFilters":
        def _date(s: str) -> date | None:
            if not s:
                return None
            try:
                return datetime.strptime(s, "%Y-%m-%d").date()
            except ValueError:
                return None

        def _int(s: str) -> int | None:
            if not s:
                return None
            try:
                return int(s)
            except ValueError:
                return None

        sign_raw = (args.get("sign") or "").strip().lower()
        sign: Literal["", "credit", "debit"]
        if sign_raw == "credit":
            sign = "credit"
        elif sign_raw == "debit":
            sign = "debit"
        else:
            sign = ""
        return cls(
            posted_from=_date(args.get("posted_from", "")),
            posted_to=_date(args.get("posted_to", "")),
            account_id=_int(args.get("account_id", "")),
            category_slug=(args.get("category_slug") or "").strip(),
            sign=sign,
            q=(args.get("q") or "").strip(),
            uncategorized_only=str(
                args.get("uncategorized_only") or ""
            ).lower() in ("1", "true", "yes"),
        )


def list_transactions(
    db: Session, store_ids: Iterable[int], filters: BankTransactionFilters,
    *, page: int = 1, per_page: int = 100,
) -> tuple[list[BankTransaction], int]:
    """Return `(rows, total)`. Sorted by `posted_at` desc with id
    tie-break for stable ordering. Paginated 1-indexed; out-of-range
    pages clamp to the last page.
    """
    q = db.query(BankTransaction).filter(
        BankTransaction.store_id.in_(store_ids),
    )
    f = filters
    if f.posted_from:
        q = q.filter(BankTransaction.posted_at >= datetime.combine(
            f.posted_from, datetime.min.time(),
        ))
    if f.posted_to:
        # End of day so the same-day rows count.
        q = q.filter(BankTransaction.posted_at <= datetime.combine(
            f.posted_to, datetime.max.time(),
        ))
    if f.account_id is not None:
        q = q.filter(BankTransaction.stripe_bank_account_id == f.account_id)
    if f.category_slug:
        q = q.filter(BankTransaction.category_slug == f.category_slug)
    if f.uncategorized_only:
        q = q.filter(BankTransaction.category_slug == "")
    if f.sign == "credit":
        q = q.filter(BankTransaction.amount_cents > 0)
    elif f.sign == "debit":
        q = q.filter(BankTransaction.amount_cents < 0)
    if f.q:
        q = q.filter(BankTransaction.description.ilike(f"%{f.q}%"))

    q = q.order_by(BankTransaction.posted_at.desc(), BankTransaction.id.desc())

    total = q.count()
    if total == 0:
        return [], 0
    total_pages = max(1, (total + per_page - 1) // per_page)
    page = max(1, min(page, total_pages))
    rows = q.offset((page - 1) * per_page).limit(per_page).all()
    return rows, total


def sum_amount_cents_by_category(
    db: Session, store_ids: Iterable[int], category_slug: str,
    *, posted_from: date | None = None, posted_to: date | None = None,
) -> int:
    """Σ |amount_cents| for transactions tagged with `category_slug`
    in the given window. Returns absolute value because the Σ is
    consumed by the monthly P&L card which displays positive numbers
    (the "amount we paid in fees"). Empty-set returns 0."""
    q = db.query(
        func.coalesce(func.sum(func.abs(BankTransaction.amount_cents)), 0)
    ).filter(
        BankTransaction.store_id.in_(store_ids),
        BankTransaction.category_slug == category_slug,
    )
    if posted_from:
        q = q.filter(BankTransaction.posted_at >= datetime.combine(
            posted_from, datetime.min.time(),
        ))
    if posted_to:
        q = q.filter(BankTransaction.posted_at <= datetime.combine(
            posted_to, datetime.max.time(),
        ))
    return int(q.scalar() or 0)
