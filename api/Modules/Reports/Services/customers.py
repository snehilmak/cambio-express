"""Customer-driven services.

Migrated from `app.py::_top_customers_data`. Group by
`Transfer.customer_id`, then resolve the FK to the `Customer` row
in a single in-clause lookup so the per-row template can show the
sender's name + phone.

Walk-in transfers (no `customer_id`) get bucketed as `"(walk-in)"`
— they can't be tracked across visits, but their volume should
still appear so the totals row matches the dashboard.
"""
from typing import Iterable

from sqlalchemy.orm import Session

from api.Modules.Reports.Models import Customer, Transfer
from api.Modules.Reports.Repositories.transfers import aggregate


def top_customers(
    db: Session,
    store_ids: Iterable[int],
    d_from,
    d_to,
    *,
    sort_by: str = "sent",
    limit: int = 50,
) -> tuple[list[dict], dict]:
    """Top `limit` customers by `sort_by` (defaults to `sent`).

    `sort_by="sent"` → biggest spenders first. `sort_by="count"` →
    most-active senders first. Other values are passed through to
    `sorted()` so callers can extend without modifying this fn.

    Returns rows with `customer` (display name) + `phone` (E.164-ish:
    country + number, or empty if the row has no phone).
    """
    rows, totals = aggregate(db, store_ids, d_from, d_to, Transfer.customer_id)
    cust_ids = [r["key"] for r in rows if r["key"] is not None]
    customers = (
        {c.id: c for c in db.query(Customer).filter(Customer.id.in_(cust_ids)).all()}
        if cust_ids else {}
    )
    for r in rows:
        cid = r.pop("key")
        if cid is None:
            r["customer"] = "(walk-in)"
            r["phone"] = ""
        else:
            c = customers.get(cid)
            if c:
                r["customer"] = c.full_name or "(no name)"
                r["phone"] = (
                    f"{c.phone_country}{c.phone_number}"
                    if c.phone_number else ""
                )
            else:
                r["customer"] = f"Customer #{cid}"
                r["phone"] = ""
    rows.sort(key=lambda r: r[sort_by], reverse=True)
    return rows[:limit], totals
