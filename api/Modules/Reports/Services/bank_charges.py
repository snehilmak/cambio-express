"""Bank-charges-by-account report aggregator.

Sums `BankTransaction` rows tagged as bank charges, grouped by
account — the data behind the "Bank Charges by Account" report
on the per-store reports page.

Uses a prefix match on `category_slug` so the static
`bank_charge` slug AND every per-account `bank_charge_<last4>`
slug roll up here.

Pure DB read — no commits, no side-effects.
"""
from datetime import date

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from api.Modules.Reports.Services.date_helpers import day_end, day_start


def bank_charges_by_account(
    db: Session,
    store_ids: list[int],
    d_from: date,
    d_to: date,
) -> tuple[list[dict], dict]:
    """Sum `BankTransaction` rows tagged as bank charges,
    grouped by account.

    Returns `(rows, totals)`:
      - rows: per-account dicts with `account`, `last4`, `count`,
        `amount`, `avg`. Sorted by amount descending so the
        biggest contributor reads first.
      - totals: `{"count": ..., "amount": ...}`.

    Empty `store_ids` → empty rows + zero totals (caller doesn't
    need to short-circuit).
    """
    from api.Modules.BankSync.Models import BankTransaction, StripeBankAccount

    if not store_ids:
        return [], {"count": 0, "amount": 0.0}

    month_start = day_start(d_from)
    month_end = day_end(d_to)
    rows_q = (
        db.query(
            BankTransaction.stripe_bank_account_id,
            func.count(BankTransaction.id),
            func.coalesce(func.sum(BankTransaction.amount_cents), 0),
        )
        .filter(
            BankTransaction.store_id.in_(store_ids),
            BankTransaction.posted_at >= month_start,
            BankTransaction.posted_at <= month_end,
            or_(
                BankTransaction.category_slug == "bank_charge",
                BankTransaction.category_slug.like("bank_charge_%"),
            ),
        )
        .group_by(BankTransaction.stripe_bank_account_id)
        .all()
    )
    acct_ids = [aid for aid, *_ in rows_q if aid is not None]
    accounts = (
        {
            a.id: a for a in
            db.query(StripeBankAccount)
              .filter(StripeBankAccount.id.in_(acct_ids))
              .all()
        }
        if acct_ids else {}
    )

    rows: list[dict] = []
    totals = {"count": 0, "amount": 0.0}
    for aid, count, cents in rows_q:
        c = int(count or 0)
        amt = abs(float(cents or 0)) / 100.0
        a = accounts.get(aid)
        rows.append({
            "account": a.label if a else "(no account)",
            "last4":   a.last4 if a else "",
            "count":   c,
            "amount":  amt,
            "avg":     (amt / c) if c else 0.0,
        })
        totals["count"] += c
        totals["amount"] += amt
    rows.sort(key=lambda r: r["amount"], reverse=True)
    return rows, totals
