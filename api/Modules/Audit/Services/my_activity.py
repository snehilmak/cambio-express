"""My-activity feed Service.

Returns audit rows authored by a specific user across every store
they've touched. Used by `GET /api/v2/auth/activity` to power the
SPA's `/app/account/activity` page — a per-user filtered view of
the same `OperatorAuditLog` + `TransferAudit` tables that the
admin audit log surfaces store-wide.

Differences from `Admin.Services.audit_log.list_audit_rows`:

* Cross-store. A cashier who worked at Store A and Store B sees
  rows from both. Filter is on `user_id`, not `store_id`.
* No `store_users` dropdown in the payload — the feed is pinned
  to one user, the filter would be meaningless.
* Each row carries `store_name` so the SPA can show which store
  the action happened at.

Pure read; no commits.
"""
from sqlalchemy.orm import Session
from typing import Any

PER_PAGE = 50


def list_my_activity(
    db: Session, *, user_id: int,
    target_filter: str = "",
    action_filter: str = "",
    page: int = 1,
) -> dict[str, Any]:
    """Return a page of audit rows authored by `user_id`."""
    from api.Modules.Audit.Models import OperatorAuditLog, TransferAudit
    from api.Modules.Tenancy.Models import Store

    op_q = db.query(OperatorAuditLog).filter_by(user_id=user_id)
    tx_q = db.query(TransferAudit).filter_by(user_id=user_id)

    if target_filter:
        op_q = op_q.filter_by(target_type=target_filter)
        if target_filter != "transfer":
            from sqlalchemy import false
            tx_q = tx_q.filter(false())

    if action_filter:
        op_q = op_q.filter_by(action=action_filter)
        tx_q = tx_q.filter_by(action=action_filter)

    op_rows = (
        op_q.order_by(OperatorAuditLog.created_at.desc()).limit(500).all()
    )
    tx_rows = (
        tx_q.order_by(TransferAudit.created_at.desc()).limit(500).all()
    )

    store_ids = (
        {r.store_id for r in op_rows if r.store_id}
        | {r.store_id for r in tx_rows if r.store_id}
    )
    stores = (
        {s.id: s for s in db.query(Store).filter(Store.id.in_(store_ids)).all()}
        if store_ids else {}
    )

    def _store_name(sid: int | None) -> str:
        if sid is None:
            return ""
        s = stores.get(sid)
        return (s.name if s else "") or ""

    merged: list[dict] = []
    for r in op_rows:
        merged.append({
            "ts":           r.created_at.isoformat() if r.created_at else "",
            "action":       r.action or "",
            "target_type":  r.target_type or "",
            "target_id":    r.target_id or "",
            "target_label": r.target_label or "",
            "summary":      r.summary or "",
            "source":       "operator",
            "store_id":     int(r.store_id) if r.store_id else 0,
            "store_name":   _store_name(r.store_id),
        })
    for r in tx_rows:
        merged.append({
            "ts":           r.created_at.isoformat() if r.created_at else "",
            "action":       r.action or "",
            "target_type":  "transfer",
            "target_id":    str(r.transfer_id),
            "target_label": (
                r.summary[:80] if r.summary else f"Transfer #{r.transfer_id}"
            ),
            "summary":      r.summary or "",
            "source":       "transfer",
            "store_id":     int(r.store_id) if r.store_id else 0,
            "store_name":   _store_name(r.store_id),
        })
    merged.sort(key=lambda x: x["ts"], reverse=True)

    total = len(merged)
    total_pages = max(1, (total + PER_PAGE - 1) // PER_PAGE)
    page = max(1, min(page, total_pages))
    start = (page - 1) * PER_PAGE
    page_rows = merged[start:start + PER_PAGE]

    return {
        "rows":         page_rows,
        "total":        total,
        "page":         page,
        "per_page":     PER_PAGE,
        "total_pages":  total_pages,
    }
