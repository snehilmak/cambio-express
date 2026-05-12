"""Money-transfer auto-fill for the daily-book editor.

Aggregates rows from the `transfer` table by company for a given
(store_id, send_date) so the React editor can pre-fill the Money
Transfer panel without the cashier re-keying numbers that the
employee transfer log already captured.

Pure read — no DB writes. The Daily Book editor surfaces this as a
read-only "auto" view; if the operator wants to override they edit
the `money_transfer` field on the receipts tab and that value wins.

Cancelled transfers are excluded so a void at 4pm doesn't poison the
day's roll-up.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from sqlalchemy.orm import Session

from api.Modules.Transfers.Models import Transfer
from api.Modules.Transfers.Services import (
    DEFAULT_MT_COMPANIES,
    store_mt_companies,
)


@dataclass
class CompanyTotals:
    """One company's roll-up for the day. Mirrors the editable
    columns the legacy Jinja MT table exposed."""
    company: str
    count: int
    amount: float
    fees: float
    federal_tax: float
    commission: float

    @property
    def total(self) -> float:
        """Combined revenue the daily-book's `money_transfer`
        line tallies: send + fees + tax + commission."""
        return (
            float(self.amount or 0) + float(self.fees or 0)
            + float(self.federal_tax or 0) + float(self.commission or 0)
        )


@dataclass
class TransfersSummary:
    """Per-day money-transfer roll-up for one store. `companies` is
    the ordered list the cashier sees in the UI — comes from the
    Store.companies CSV with the historical default as fallback."""
    companies: list[str]
    by_company: list[CompanyTotals]
    grand_total: float


def _resolve_store_companies(db: Session, store_id: int) -> list[str]:
    """Read the Store.companies CSV. Falls back to the historical
    default when the row is missing or the CSV is empty."""
    # Defer import — keeps this module out of the Flask app circular
    # graph during the FastAPI mount step at boot.
    from app import Store

    store = db.get(Store, int(store_id))
    return store_mt_companies(store) if store else list(DEFAULT_MT_COMPANIES)


def summarize_transfers_for_day(
    db: Session, store_id: int, report_date: date,
) -> TransfersSummary:
    """Aggregate `transfer` rows for one (store_id, send_date) by
    company. Returns one CompanyTotals per active company, even
    when zero transfers were logged that day — the editor needs
    every row to render the auto-fill table consistently."""
    rows = (
        db.query(Transfer)
          .filter(Transfer.store_id == int(store_id))
          .filter(Transfer.send_date == report_date)
          .filter(Transfer.status != "Cancelled")
          .all()
    )

    companies = _resolve_store_companies(db, store_id)

    # Bucket by company name. Unknown companies (operator deleted a
    # company from the store config after older transfers were logged)
    # still get a row at the bottom so the totals match.
    buckets: dict[str, CompanyTotals] = {
        c: CompanyTotals(company=c, count=0, amount=0.0,
                         fees=0.0, federal_tax=0.0, commission=0.0)
        for c in companies
    }
    for t in rows:
        co = (t.company or "").strip()
        if not co:
            continue
        bucket = buckets.get(co)
        if bucket is None:
            bucket = CompanyTotals(
                company=co, count=0, amount=0.0,
                fees=0.0, federal_tax=0.0, commission=0.0,
            )
            buckets[co] = bucket
        bucket.count += 1
        bucket.amount      += float(t.send_amount or 0)
        bucket.fees        += float(t.fee or 0)
        bucket.federal_tax += float(t.federal_tax or 0)
        bucket.commission  += float(t.commission or 0)

    # Preserve the configured company order; trailing unknown
    # companies (carried-over historical entries) appear alphabetically.
    ordered: list[CompanyTotals] = [buckets[c] for c in companies]
    extras = sorted(
        (b for name, b in buckets.items() if name not in companies),
        key=lambda b: b.company.lower(),
    )
    ordered.extend(extras)

    grand_total = sum(b.total for b in ordered)
    return TransfersSummary(
        companies=companies,
        by_company=ordered,
        grand_total=float(grand_total),
    )
