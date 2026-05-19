"""Sales-* services. All thin transforms over the aggregator.

Shared contract:

    fn(db: Session, store_ids, d_from, d_to) -> (rows, totals)

Rows come back sorted (by sent desc) and the grouping key is
renamed from the generic ``key`` to a meaningful column name
(``company``, ``service_type``, etc.) for the response shape.

If a future report needs the unsorted / generic rows, it goes
straight to `Repositories.transfers.aggregate` — services exist
specifically because the rename + sort is presentation-layer logic
that doesn't belong in the repository.
"""
from typing import Any, Iterable

from sqlalchemy.orm import Session

from api.Modules.Reports.Models import Transfer
from api.Modules.Reports.Repositories.transfers import aggregate


def sales_by_company(
    db: Session, store_ids: Iterable[int], d_from, d_to,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Group active transfers by `Transfer.company`.

    Returns rows tagged with a `company` field (renamed from the
    repository's generic `key`), sorted by sent desc. Empty company
    string becomes `"(no company)"` so the row is visible — it
    tracks legacy data that never had a company tag.
    """
    rows, totals = aggregate(db, store_ids, d_from, d_to, Transfer.company)
    for r in rows:
        r["company"] = r.pop("key") or "(no company)"
    rows.sort(key=lambda r: r["sent"], reverse=True)
    return rows, totals


def sales_by_service(
    db: Session, store_ids: Iterable[int], d_from, d_to,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Group by `Transfer.service_type` (Money Transfer / Bill
    Payment / Top Up / Recharge)."""
    rows, totals = aggregate(db, store_ids, d_from, d_to, Transfer.service_type)
    for r in rows:
        r["service_type"] = r.pop("key") or "(no service)"
    rows.sort(key=lambda r: r["sent"], reverse=True)
    return rows, totals


def by_destination_country(
    db: Session, store_ids: Iterable[int], d_from, d_to,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Group by `Transfer.country`. Rows with empty country are
    bucketed as `"(no country)"`."""
    rows, totals = aggregate(db, store_ids, d_from, d_to, Transfer.country)
    for r in rows:
        r["country"] = r.pop("key") or "(no country)"
    rows.sort(key=lambda r: r["sent"], reverse=True)
    return rows, totals


def top_recipients(
    db: Session, store_ids: Iterable[int], d_from, d_to, *, limit: int = 50,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Group by `Transfer.recipient_name` string.

    Recipients aren't stored in their own table — `Transfer.recipient_name`
    is the only signal — so we just group on the string. Empty names
    bucketed as `"(no name)"`. Top `limit` rows by sent desc.

    Note: the totals reflect EVERY group, not just the top `limit`,
    so the percentage-of-total math the template does stays accurate
    when the user picks a small limit.
    """
    rows, totals = aggregate(
        db, store_ids, d_from, d_to, Transfer.recipient_name,
    )
    for r in rows:
        r["recipient"] = r.pop("key") or "(no name)"
    rows.sort(key=lambda r: r["sent"], reverse=True)
    return rows[:limit], totals
