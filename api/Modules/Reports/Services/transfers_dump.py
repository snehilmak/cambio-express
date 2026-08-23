"""Raw transfers dump for the Data Export page.

The export page has offered a "Transfers CSV" download since the
Report Center shipped, but the `transfers` slug never existed in
the CSV registry — the button 404'd in production. This service
backs it: every transfer in the window, one row each, newest
first, with the money identity columns an accountant or auditor
asks for (send / fee / federal tax / total collected — invariant
#9's terms).
"""
from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy.orm import Session

from api.Modules.Transfers.Models import Transfer


def transfers_dump(
    db: Session, store_ids: list[int], d_from: date, d_to: date,
    **_: Any,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    q = (
        db.query(Transfer)
        .filter(
            Transfer.store_id.in_(store_ids),
            Transfer.send_date >= d_from,
            Transfer.send_date <= d_to,
        )
        .order_by(Transfer.send_date.desc(), Transfer.id.desc())
    )
    rows = []
    total_sent = total_fees = total_tax = 0
    count = 0
    for t in q.all():
        rows.append({
            "send_date": t.send_date,
            "sender_name": t.sender_name or "",
            "recipient_name": t.recipient_name or "",
            "country": t.country or "",
            "company": t.company or "",
            "service_type": t.service_type or "",
            "send_amount": (t.send_amount_cents or 0) / 100.0,
            "fee": (t.fee_cents or 0) / 100.0,
            "federal_tax": (t.federal_tax_cents or 0) / 100.0,
            "total_collected": (t.total_collected_cents or 0) / 100.0,
            "status": t.status or "",
            "confirm": t.confirm_number or "",
        })
        count += 1
        total_sent += int(t.send_amount_cents or 0)
        total_fees += int(t.fee_cents or 0)
        total_tax += int(t.federal_tax_cents or 0)
    return rows, {
        "count": count,
        "sent": total_sent / 100.0,
        "fees": total_fees / 100.0,
        "tax": total_tax / 100.0,
    }
