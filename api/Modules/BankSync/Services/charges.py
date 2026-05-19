"""Bank-charges aggregation Service.

Pure-DB readers used by the monthly P&L:

  - `bank_charges_for_month`: scalar sum of absolute amounts for
    a single category (or a prefix family). Feeds the
    `MonthlyFinancial.bank_charges_total` auto-fill and per-account
    P&L lines (bank_charges_210 / 230 / etc).
  - `bank_charges_breakdown_for_month`: two-level group-by
    description for the expandable Bank Charges block on the P&L.
    Sorted by total descending.

Both functions accept a SQLAlchemy `Session` so callers can run
them outside the Flask app context (CLI exports, tests, future
FastAPI controllers).
"""
from calendar import monthrange
from datetime import datetime
from typing import Any

from sqlalchemy import or_, func
from sqlalchemy.orm import Session

from api.Modules.BankSync.Models import BankTransaction, StripeBankAccount


def bank_charges_for_month(
    db: Session,
    store_id: int,
    year: int,
    month: int,
    category_slug: str | None = None,
    *,
    prefix: str | None = None,
) -> float:
    """Sum the absolute amount of `BankTransaction` rows tagged for
    the given month.

    Pass either an exact `category_slug` or a `prefix` (used by
    the bank-charges P&L feed to roll up every per-account slug
    like `bank_charge / bank_charge_210 / bank_charge_<last4>` in
    one query).

    Stored amounts are signed (debits negative); P&L expense
    columns use positive numbers, so we abs(). Returns 0.0 when
    no transactions match — the monthly_report route only LOCKs
    the P&L field when this is > 0, leaving the manual value in
    place for stores without bank sync.
    """
    month_start = datetime(year, month, 1)
    month_end_d = monthrange(year, month)[1]
    month_end = datetime(year, month, month_end_d, 23, 59, 59)
    q = db.query(
        func.coalesce(func.sum(BankTransaction.amount_cents), 0)
    ).filter(
        BankTransaction.store_id == store_id,
        BankTransaction.posted_at >= month_start,
        BankTransaction.posted_at <= month_end,
    )
    if prefix is not None:
        # SQL prefix match. Trailing % does the heavy lifting; we
        # also accept the bare prefix itself (no underscore suffix)
        # so the legacy `bank_charge` slug counts.
        q = q.filter(or_(
            BankTransaction.category_slug == prefix,
            BankTransaction.category_slug.like(f"{prefix}_%"),
        ))
    else:
        q = q.filter(BankTransaction.category_slug == category_slug)
    cents = q.scalar()
    return abs(float(cents or 0)) / 100.0


def bank_charges_breakdown_for_month(
    db: Session, store_id: int, year: int, month: int,
) -> list[dict[str, Any]]:
    """Two-level breakdown feeding the expandable Bank Charges
    block on the monthly P&L.

    Groups bank-charge transactions by description string; each
    group exposes its individual rows.

    Returns a list of dicts:
      [
        {"description": "REMOTE DEPOSIT FEE",
         "total":       2.10,
         "count":       1,
         "transactions": [
           {"posted_at":     datetime,
            "amount":        2.10,
            "account_label": "••0230" or nickname,
            "description":   "REMOTE DEPOSIT FEE 04/29"},
         ]},
        ...
      ]

    Sorted by total descending so the biggest contributor reads
    first. Uses a prefix match on `bank_charge%` so every
    per-account slug (`bank_charge_210`, `bank_charge_230`, future
    `bank_charge_<last4>`) rolls into the breakdown without
    explicit registry maintenance.
    """
    month_start = datetime(year, month, 1)
    month_end_d = monthrange(year, month)[1]
    month_end = datetime(year, month, month_end_d, 23, 59, 59)
    rows = (
        db.query(BankTransaction)
          .filter(
              BankTransaction.store_id == store_id,
              or_(
                  BankTransaction.category_slug == "bank_charge",
                  BankTransaction.category_slug.like("bank_charge_%"),
              ),
              BankTransaction.posted_at >= month_start,
              BankTransaction.posted_at <= month_end,
          )
          .order_by(BankTransaction.posted_at.desc())
          .all()
    )
    if not rows:
        return []
    # Map account ids → row to avoid N+1 lookup per transaction.
    acct_ids = {
        r.stripe_bank_account_id for r in rows
        if r.stripe_bank_account_id
    }
    if acct_ids:
        accts = {
            a.id: a for a in db.query(StripeBankAccount)
                                 .filter(StripeBankAccount.id.in_(acct_ids))
                                 .all()
        }
    else:
        accts = {}
    # Group by description. The exact full description is the key
    # — operators want each variant visible (e.g. "REMOTE DEPOSIT
    # FEE 04/29" and "REMOTE DEPOSIT FEE 05/02" group separately
    # if the bank includes the date in the string).
    groups: dict[str, dict[str, Any]] = {}
    for r in rows:
        key = str(r.description or "(no description)")
        g = groups.setdefault(key, {
            "description": key,
            "total": 0.0,
            "count": 0,
            "transactions": [],
        })
        amt = abs(float(r.amount_cents or 0) / 100.0)
        g["total"] += amt
        g["count"] += 1
        acct = accts.get(r.stripe_bank_account_id)
        g["transactions"].append({
            "posted_at": r.posted_at,
            "amount": amt,
            "description": r.description or "",
            "account_label": acct.label if acct else "",
        })
    return sorted(
        groups.values(), key=lambda g: g["total"], reverse=True,
    )
