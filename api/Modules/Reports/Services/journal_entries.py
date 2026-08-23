"""Journal-entry export (P1-8 phase A — accounting export).

Turns booked day-close data into double-entry journal lines an
accountant can import into any ledger (QuickBooks/Xero "journal
entry" CSV shape): one entry per business day, lines carrying
date / account / debit / credit / memo.

Per day, from the day's RegisterClose rows (manual or imported —
provenance doesn't matter):

    debit  Cash on hand                Σ cash tenders
    debit  Card settlements receivable Σ card tenders
    debit  Other tenders               Σ other tenders
    credit Sales — <department>        per department-sales line
    credit Sales — unclassified        gross − Σ department lines
    credit Sales tax payable           Σ sales tax
    debit/credit Cash over/short       whatever balances the entry

Every entry balances by construction — the over/short line
absorbs the tender-vs-sales variance the day-close module
deliberately surfaces instead of blocking. Department names come
from the store's own catalog (the operator-owned vocabulary,
HANDOFF.md §2); account labels are the fixed neutral set above
until the QuickBooks phase introduces a per-store chart-of-
accounts mapping.

Negative sums (refund-heavy days) flip sides rather than emitting
negative amounts — ledgers reject negative debits.

MSB daily-book journals are deliberately NOT in phase A — the
daily book's cash ledger needs its own mapping conversation and
lands with the QuickBooks phase.
"""
from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy.orm import Session

from api.Modules.DayClose.Models import RegisterClose


ACCT_CASH = "Cash on hand"
ACCT_CARD = "Card settlements receivable"
ACCT_OTHER = "Other tenders"
ACCT_TAX = "Sales tax payable"
ACCT_OVER_SHORT = "Cash over/short"
ACCT_SALES_UNCLASSIFIED = "Sales — unclassified"


def _line(
    day: date, account: str, *, debit: int = 0, credit: int = 0,
    memo: str = "",
) -> dict[str, Any]:
    """One journal line, cents in, dollars out. Negative amounts
    flip to the opposite side so the CSV never carries a negative
    debit/credit."""
    if debit < 0:
        debit, credit = 0, credit - debit
    if credit < 0:
        debit, credit = debit - credit, 0
    return {
        "date": day,
        "account": account,
        "debit": debit / 100.0,
        "credit": credit / 100.0,
        "memo": memo,
    }


def journal_entries(
    db: Session, store_ids: list[int], d_from: date, d_to: date,
    **_: Any,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    closes = (
        db.query(RegisterClose)
        .filter(
            RegisterClose.store_id.in_(store_ids),
            RegisterClose.report_date >= d_from,
            RegisterClose.report_date <= d_to,
        )
        .order_by(RegisterClose.report_date, RegisterClose.register_label)
        .all()
    )

    # Group by business day (aggregating across the requested
    # stores, like every other report service).
    by_day: dict[date, list[RegisterClose]] = {}
    for c in closes:
        by_day.setdefault(c.report_date, []).append(c)

    rows: list[dict[str, Any]] = []
    total_debits = 0
    total_credits = 0
    for day in sorted(by_day):
        day_closes = by_day[day]
        cash = sum(int(c.cash_total_cents or 0) for c in day_closes)
        card = sum(int(c.card_total_cents or 0) for c in day_closes)
        other = sum(int(c.other_total_cents or 0) for c in day_closes)
        gross = sum(int(c.gross_sales_cents or 0) for c in day_closes)
        tax = sum(int(c.sales_tax_cents or 0) for c in day_closes)

        dept_cents: dict[str, int] = {}
        for c in day_closes:
            for line in c.department_sales:
                name = line.department.name or "?"
                dept_cents[name] = (
                    dept_cents.get(name, 0) + int(line.amount_cents or 0)
                )

        memo = f"Day close {day.isoformat()}"
        entry: list[dict[str, Any]] = []
        if cash:
            entry.append(_line(day, ACCT_CASH, debit=cash, memo=memo))
        if card:
            entry.append(_line(day, ACCT_CARD, debit=card, memo=memo))
        if other:
            entry.append(_line(day, ACCT_OTHER, debit=other, memo=memo))
        for name in sorted(dept_cents):
            if dept_cents[name]:
                entry.append(_line(
                    day, f"Sales — {name}",
                    credit=dept_cents[name], memo=memo,
                ))
        unclassified = gross - sum(dept_cents.values())
        if unclassified:
            entry.append(_line(
                day, ACCT_SALES_UNCLASSIFIED,
                credit=unclassified, memo=memo,
            ))
        if tax:
            entry.append(_line(day, ACCT_TAX, credit=tax, memo=memo))

        # Balance the entry: tenders vs (sales + tax). The day-close
        # module surfaces this variance instead of blocking it — the
        # journal books it to over/short so the entry still balances.
        variance = (cash + card + other) - (gross + tax)
        if variance:
            entry.append(_line(
                day, ACCT_OVER_SHORT, credit=variance, memo=memo,
            ))

        for row in entry:
            total_debits += round(row["debit"] * 100)
            total_credits += round(row["credit"] * 100)
        rows.extend(entry)

    return rows, {
        "debits": total_debits / 100.0,
        "credits": total_credits / 100.0,
        "days": len(by_day),
    }
