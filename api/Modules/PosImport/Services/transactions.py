"""PosImport — transaction browsing (G-6).

Read-only queries over the ``pos_transaction`` family. These rows
are derived from the staged journal files on every commit, so this
module never writes: it exists so an operator can answer "what sold
on this ticket?" and "which tickets had an item voided?".

One rule runs through all of it: **a cancelled line is real data.**
It is returned to the caller and flagged, because a voided item is
precisely what a manager is looking for — but it is never summed.
Every money figure here comes from the parent event's own totals,
which the parser already computed with cancelled lines excluded.
"""
from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import func, or_
from sqlalchemy.orm import Session, selectinload

from api.Core.Money import to_dollars
from api.Modules.PosImport.Models import (
    PosTransaction, PosTransactionLine,
)

# Guard rails on the list query. A c-store runs a few thousand
# tickets a day, so an unbounded range would page through months of
# rows to render one screen.
MAX_RANGE_DAYS = 92
MAX_PER_PAGE = 200


class TransactionQueryError(Exception):
    """User-safe failure (bad range, unknown filter…)."""


def _stamp(value: Any) -> str | None:
    return value.isoformat() if value is not None else None


def _base_query(
    db: Session, store_id: int, start: date, end: date, *,
    q: str = "", kind: str = "", register_id: str = "",
    voided_only: bool = False,
) -> Any:
    query = db.query(PosTransaction).filter(
        PosTransaction.store_id == store_id,
        PosTransaction.business_date >= start,
        PosTransaction.business_date <= end,
    )
    if kind:
        query = query.filter(PosTransaction.kind == kind)
    if register_id:
        query = query.filter(PosTransaction.register_id == register_id)
    if voided_only:
        query = query.filter(PosTransaction.has_voided_line.is_(True))
    needle = q.strip()
    if needle:
        # Ticket number and cashier are what an operator actually has
        # in hand (off a receipt or a shift report); item description
        # is the "what did they buy" case, so it searches the lines.
        line_hits = (
            db.query(PosTransactionLine.transaction_id)
            .filter(
                PosTransactionLine.store_id == store_id,
                func.lower(PosTransactionLine.description)
                .contains(needle.lower()),
            )
        )
        query = query.filter(or_(
            PosTransaction.transaction_no.contains(needle),
            PosTransaction.cashier_id.contains(needle),
            PosTransaction.id.in_(line_hits),
        ))
    return query


def list_transactions(
    db: Session, store_id: int, start: date, end: date, *,
    q: str = "", kind: str = "", register_id: str = "",
    voided_only: bool = False, page: int = 1, per_page: int = 50,
) -> dict[str, Any]:
    """One page of tickets, newest first, plus totals for the WHOLE
    filtered set.

    The totals deliberately span every matching row rather than the
    page: a footer that only added up the visible rows would
    disagree with the count beside it and read as a bug.
    """
    if end < start:
        raise TransactionQueryError("end must not be before start.")
    if (end - start).days > MAX_RANGE_DAYS:
        raise TransactionQueryError(
            f"Range is limited to {MAX_RANGE_DAYS} days.",
        )
    per_page = max(1, min(int(per_page or 50), MAX_PER_PAGE))
    page = max(1, int(page or 1))

    query = _base_query(
        db, store_id, start, end, q=q, kind=kind,
        register_id=register_id, voided_only=voided_only,
    )
    total = query.count()
    total_grand_cents = (
        query.with_entities(
            func.coalesce(func.sum(PosTransaction.grand_total_cents), 0),
        ).scalar() or 0
    )
    # Counted with a filter rather than SUM(boolean): summing a bool
    # works on SQLite and Postgres by different rules, and this stays
    # honest on both.
    voided_count = query.filter(
        PosTransaction.has_voided_line.is_(True),
    ).count()
    rows = (
        query
        .order_by(
            PosTransaction.business_date.desc(),
            PosTransaction.receipt_at.desc(),
            PosTransaction.id.desc(),
        )
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )
    # One grouped count for the page rather than N per-row queries.
    counts = dict(
        db.query(
            PosTransactionLine.transaction_id,
            func.count(PosTransactionLine.id),
        )
        .filter(PosTransactionLine.transaction_id.in_([r.id for r in rows]))
        .group_by(PosTransactionLine.transaction_id)
        .all(),
    ) if rows else {}

    return {
        "rows": [
            {
                "id": t.id,
                "business_date": t.business_date.isoformat(),
                "kind": t.kind or "",
                "register_id": t.register_id or "",
                "cashier_id": t.cashier_id or "",
                "transaction_no": t.transaction_no or "",
                "receipt_at": _stamp(t.receipt_at),
                "item_count": int(counts.get(t.id, 0)),
                "gross": to_dollars(t.gross_cents),
                "tax": to_dollars(t.tax_cents),
                "grand_total": to_dollars(t.grand_total_cents),
                "has_voided_line": bool(t.has_voided_line),
                "training_mode": bool(t.training_mode),
                "offline": bool(t.offline),
                "suspended": bool(t.suspended),
            }
            for t in rows
        ],
        "total": total,
        "page": page,
        "total_pages": max(1, (total + per_page - 1) // per_page),
        "total_grand": to_dollars(int(total_grand_cents)),
        "voided_count": voided_count,
    }


def transaction_detail(
    db: Session, store_id: int, transaction_id: int,
) -> dict[str, Any] | None:
    """One ticket with every line and tender.

    Cancelled lines come back with ``status="cancel"`` rather than
    being filtered out — seeing the void IS the point. The money
    fields on the event exclude them already.
    """
    txn = (
        db.query(PosTransaction)
        .options(
            selectinload(PosTransaction.lines),
            selectinload(PosTransaction.tenders),
        )
        .filter(
            PosTransaction.id == transaction_id,
            PosTransaction.store_id == store_id,
        )
        .first()
    )
    if txn is None:
        return None
    return {
        "id": txn.id,
        "business_date": txn.business_date.isoformat(),
        "source_file": txn.source_file or "",
        "kind": txn.kind or "",
        "register_id": txn.register_id or "",
        "cashier_id": txn.cashier_id or "",
        "till_id": txn.till_id or "",
        "transaction_no": txn.transaction_no or "",
        "event_sequence_id": txn.event_sequence_id or "",
        "started_at": _stamp(txn.started_at),
        "ended_at": _stamp(txn.ended_at),
        "receipt_at": _stamp(txn.receipt_at),
        "outside": bool(txn.outside),
        "training_mode": bool(txn.training_mode),
        "offline": bool(txn.offline),
        "suspended": bool(txn.suspended),
        "gross": to_dollars(txn.gross_cents),
        "net": to_dollars(txn.net_cents),
        "tax": to_dollars(txn.tax_cents),
        "grand_total": to_dollars(txn.grand_total_cents),
        "has_voided_line": bool(txn.has_voided_line),
        "lines": [
            {
                "line_seq": int(line.line_seq or 0),
                "status": line.status or "normal",
                "pos_code": line.pos_code or "",
                "description": line.description or "",
                "entry_method": line.entry_method or "",
                "merchandise_code": line.merchandise_code or "",
                "quantity": float(line.quantity or 0.0),
                "amount": to_dollars(line.amount_cents),
                "actual_price": to_dollars(line.actual_price_cents),
                "regular_price": to_dollars(line.regular_price_cents),
                "is_fuel": bool(line.is_fuel),
                "fuel_grade_id": line.fuel_grade_id or "",
                "fuel_position": line.fuel_position or "",
                "gallons": float(line.gallons or 0.0),
            }
            for line in sorted(txn.lines, key=lambda l: int(l.line_seq or 0))
        ],
        "tenders": [
            {
                "code": tender.code or "",
                "sub_code": tender.sub_code or "",
                "amount": to_dollars(tender.amount_cents),
                "is_change": bool(tender.is_change),
                "status": tender.status or "normal",
            }
            for tender in txn.tenders
        ],
    }


__all__ = [
    "MAX_PER_PAGE", "MAX_RANGE_DAYS", "TransactionQueryError",
    "list_transactions", "transaction_detail",
]
