"""Transfer-table CRUD helpers.

Owns the filter + sort + pagination logic for the ``/transfers``
list view. Each helper takes the ``Session`` as the first argument
(request-scoped via ``Depends(get_db)``).

The big helper is ``list_with_filters``: takes a ``TransferFilters``
dataclass and returns ``(rows, total)`` for paginated rendering.
The dataclass keeps the controller signature flat — no ``**kwargs``
smoke.
"""
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Iterable, Literal

from sqlalchemy import or_
from sqlalchemy.orm import Session

from api.Modules.Transfers.Models import Transfer


# Sort columns whitelisted on the legacy /transfers route. Slug names
# match the existing `?sort=` query strings (and the column-header
# links in `_transfers_table.html`) — don't rename without updating
# the template too.
SORT_COLUMNS: dict[str, Any] = {
    "date":      Transfer.send_date,
    "sender":    Transfer.sender_name,
    "company":   Transfer.company,
    "amount":    Transfer.send_amount,
    "recipient": Transfer.recipient_name,
    "country":   Transfer.country,
    "confirm":   Transfer.confirm_number,
    "batch":     Transfer.batch_id,
    "status":    Transfer.status,
}


@dataclass
class TransferFilters:
    """Bag of filter values from `/transfers` query string. Empty
    strings = no filter; the helper only applies a clause when the
    field is truthy. Mirrors the legacy `request.args.get` shape so
    the controller can keep its current "build a dict, pass it in"
    flow."""
    company: str = ""
    status: str = ""
    date_from: date | None = None
    date_to: date | None = None
    sender: str = ""
    recipient: str = ""
    country: str = ""
    confirm: str = ""
    batch: str = ""
    q: str = ""
    sort_slug: str = ""
    sort_dir: Literal["asc", "desc"] = "desc"

    @classmethod
    def from_query(cls, args: Any) -> "TransferFilters":
        """Build a `TransferFilters` from a Flask `request.args` (or a
        Werkzeug MultiDict, or a plain dict). Tolerates malformed
        date strings — bad input drops the filter rather than raising,
        matching the legacy route's behavior."""
        def _date(s: str) -> date | None:
            if not s:
                return None
            try:
                return datetime.strptime(s, "%Y-%m-%d").date()
            except ValueError:
                return None
        sort_dir_raw = (args.get("dir") or "desc").strip().lower()
        sort_dir: Literal["asc", "desc"] = (
            "asc" if sort_dir_raw == "asc" else "desc"
        )
        return cls(
            company=args.get("company", ""),
            status=args.get("status", ""),
            date_from=_date(args.get("date_from", "")),
            date_to=_date(args.get("date_to", "")),
            sender=(args.get("sender") or "").strip(),
            recipient=(args.get("recipient") or "").strip(),
            country=(args.get("country") or "").strip(),
            confirm=(args.get("confirm") or "").strip(),
            batch=(args.get("batch") or "").strip(),
            q=(args.get("q") or "").strip(),
            sort_slug=(args.get("sort") or "").strip(),
            sort_dir=sort_dir,
        )


def list_with_filters(
    db: Session, store_ids: Iterable[int], filters: TransferFilters,
    *, page: int = 1, per_page: int = 50,
) -> tuple[list[Transfer], int]:
    """Return `(rows, total)` for a filtered + sorted + paginated
    listing. `total` is the unpaginated row count — needed to render
    the pager.

    `page` is 1-indexed; out-of-range values clamp to the last page.
    """
    q = db.query(Transfer).filter(Transfer.store_id.in_(store_ids))

    f = filters
    if f.company:
        q = q.filter(Transfer.company == f.company)
    if f.status:
        q = q.filter(Transfer.status == f.status)
    if f.date_from:
        q = q.filter(Transfer.send_date >= f.date_from)
    if f.date_to:
        q = q.filter(Transfer.send_date <= f.date_to)
    if f.sender:
        q = q.filter(Transfer.sender_name.ilike(f"%{f.sender}%"))
    if f.recipient:
        q = q.filter(Transfer.recipient_name.ilike(f"%{f.recipient}%"))
    if f.country:
        q = q.filter(Transfer.country.ilike(f"%{f.country}%"))
    if f.confirm:
        q = q.filter(Transfer.confirm_number.ilike(f"%{f.confirm}%"))
    if f.batch:
        q = q.filter(Transfer.batch_id.ilike(f"%{f.batch}%"))
    if f.q:
        like = f"%{f.q}%"
        q = q.filter(or_(
            Transfer.sender_name.ilike(like),
            Transfer.recipient_name.ilike(like),
            Transfer.confirm_number.ilike(like),
            Transfer.country.ilike(like),
            Transfer.batch_id.ilike(like),
        ))

    # Sort — whitelisted col + direction; fall back to "newest first".
    sort_col = SORT_COLUMNS.get(f.sort_slug)
    if sort_col is not None:
        order = sort_col.asc() if f.sort_dir == "asc" else sort_col.desc()
        # Tie-break on created_at so equal-key rows have a stable order.
        q = q.order_by(order, Transfer.created_at.desc())
    else:
        q = q.order_by(Transfer.send_date.desc(), Transfer.created_at.desc())

    total = q.count()
    if total == 0:
        return [], 0

    total_pages = max(1, (total + per_page - 1) // per_page)
    page = max(1, min(page, total_pages))
    rows = q.offset((page - 1) * per_page).limit(per_page).all()
    return rows, total


def get_by_id_in_stores(
    db: Session, transfer_id: int, store_ids: Iterable[int],
) -> Transfer | None:
    """Look up a transfer by ID, scoped to a set of stores. Returns
    `None` when the row exists but lives outside the caller's scope —
    callers translate that into 404 (never 403, to avoid revealing
    that the row exists in another tenant)."""
    return (
        db.query(Transfer)
          .filter(Transfer.id == transfer_id, Transfer.store_id.in_(store_ids))
          .first()
    )
