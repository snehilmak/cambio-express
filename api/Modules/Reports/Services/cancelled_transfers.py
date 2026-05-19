"""Cancelled / rejected transfers list aggregator.

Lists `Transfer` rows whose status is in
`OWNER_TRANSFER_EXCLUDED` (currently Canceled / Rejected) over
the period. Counter-part to the active-transfer reports — this
is the operator-visibility view for sender disputes, OFAC-flagged
sends, etc.

Pure DB read — no commits, no side-effects.
"""
from datetime import date

from sqlalchemy.orm import Session
from typing import Any


def cancelled_transfers(
    db: Session,
    store_ids: list[int],
    d_from: date,
    d_to: date,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """List Canceled / Rejected transfers in the window.

    Returns `(rows, totals)`:
      - rows: per-transfer dicts with `send_date`, `sender_name`,
        `recipient_name`, `country`, `company`, `amount`,
        `status`, `status_notes`, `confirm`. Sorted by send_date
        desc, then id desc (stable newest-first).
      - totals: `count`, `amount`, plus per-status counts
        (`canceled`, `rejected`) so the template can show the
        split without re-iterating the list.
    """
    from api.Modules.Transfers.Models import Transfer
    from api.Modules.Owners.Services import OWNER_TRANSFER_EXCLUDED

    rows_q = (
        db.query(Transfer)
          .filter(
              Transfer.store_id.in_(store_ids),
              Transfer.send_date >= d_from,
              Transfer.send_date <= d_to,
              Transfer.status.in_(OWNER_TRANSFER_EXCLUDED),
          )
          .order_by(Transfer.send_date.desc(), Transfer.id.desc())
          .all()
    )
    rows = [
        {
            "send_date":      t.send_date,
            "sender_name":    t.sender_name or "",
            "recipient_name": t.recipient_name or "",
            "country":        t.country or "",
            "company":        t.company or "",
            "amount":         float(t.send_amount or 0),
            "status":         t.status or "",
            "status_notes":   t.status_notes or "",
            "confirm":        t.confirm_number or "",
        }
        for t in rows_q
    ]
    totals = {
        "count":    len(rows),
        "amount":   sum(r["amount"] for r in rows),
        "canceled": sum(1 for r in rows if r["status"] == "Canceled"),
        "rejected": sum(1 for r in rows if r["status"] == "Rejected"),
    }
    return rows, totals
