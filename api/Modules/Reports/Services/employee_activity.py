"""Employee activity report aggregator.

Per-employee audit / activity view: count + sent (active
transfers) + cancel count + last_activity timestamp. Different
from Sales by Employee in that it INCLUDES cancelled / rejected
transfers — this is an audit view (who did what) rather than a
revenue view (who earned money).

Pure DB read — no commits, no side-effects.
"""
from datetime import date

from sqlalchemy import func
from sqlalchemy.orm import Session


def employee_activity(
    db: Session,
    store_ids: list[int],
    d_from: date,
    d_to: date,
) -> tuple[list[dict], dict]:
    """Aggregate transfers by `Transfer.created_by` employee.

    Returns `(rows, totals)`:
      - rows: per-employee dicts with `employee` (display label),
        `username`, `count` (active), `sent` (active dollars),
        `cancels` (cancelled / rejected count), `last_activity`
        (max send_date across active). Unattributed transfers
        (created_by IS NULL) bucket as "(unattributed)". Sorted
        by total activity (count + cancels) desc.
      - totals: cross-employee sums of count + sent + cancels.
    """
    from api.Modules.Tenancy.Models import User
    from api.Modules.Transfers.Models import Transfer
    from api.Modules.Owners.Services import OWNER_TRANSFER_EXCLUDED

    active_q = (
        db.query(
            Transfer.created_by,
            func.count(Transfer.id),
            func.coalesce(func.sum(Transfer.send_amount), 0.0),
            func.max(Transfer.send_date),
        )
        .filter(
            Transfer.store_id.in_(store_ids),
            Transfer.send_date >= d_from,
            Transfer.send_date <= d_to,
            Transfer.status.notin_(OWNER_TRANSFER_EXCLUDED),
        )
        .group_by(Transfer.created_by)
        .all()
    )
    cancel_q = (
        db.query(
            Transfer.created_by,
            func.count(Transfer.id),
        )
        .filter(
            Transfer.store_id.in_(store_ids),
            Transfer.send_date >= d_from,
            Transfer.send_date <= d_to,
            Transfer.status.in_(OWNER_TRANSFER_EXCLUDED),
        )
        .group_by(Transfer.created_by)
        .all()
    )
    cancels_by_uid = {uid: int(c or 0) for uid, c in cancel_q}

    all_uids = (
        {uid for uid, *_ in active_q if uid is not None}
        | {uid for uid, _ in cancel_q if uid is not None}
    )
    users = (
        {u.id: u for u in db.query(User).filter(User.id.in_(all_uids)).all()}
        if all_uids else {}
    )

    rows_by_uid: dict = {}
    for uid, count, sent, last_date in active_q:
        rows_by_uid[uid] = {
            "uid":           uid,
            "count":         int(count or 0),
            "sent":          float(sent or 0),
            "cancels":       cancels_by_uid.get(uid, 0),
            "last_activity": last_date,
        }
    for uid, c in cancels_by_uid.items():
        if uid not in rows_by_uid:
            rows_by_uid[uid] = {
                "uid":           uid,
                "count":         0,
                "sent":          0.0,
                "cancels":       c,
                "last_activity": None,
            }

    rows: list[dict] = []
    for uid, r in rows_by_uid.items():
        if uid is None:
            r["employee"] = "(unattributed)"
            r["username"] = ""
        else:
            u = users.get(uid)
            r["employee"] = (
                (u.full_name or u.username) if u else f"User #{uid}"
            )
            r["username"] = u.username if u else ""
        del r["uid"]
        rows.append(r)
    rows.sort(key=lambda r: (r["count"] + r["cancels"]), reverse=True)

    totals = {
        "count":   sum(r["count"]   for r in rows),
        "sent":    sum(r["sent"]    for r in rows),
        "cancels": sum(r["cancels"] for r in rows),
    }
    return rows, totals
