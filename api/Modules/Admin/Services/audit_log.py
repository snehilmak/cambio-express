"""Admin audit-log Service.

Pulls the merged ``OperatorAuditLog`` + ``TransferAudit`` feed for
a store, applies target / action / user filters, and returns a
paginated payload the SPA renders directly.

The ``merged`` dict shape is the wire contract — every column
added here must be added to the ``AdminAuditRow`` Pydantic schema
in lockstep or the response validator will trip.
"""
from sqlalchemy.orm import Session
from typing import Any

PER_PAGE = 50


def list_audit_rows(
    db: Session, *, store_id: int,
    target_filter: str = "",
    user_filter:   str = "",
    action_filter: str = "",
    page: int = 1,
) -> dict[str, Any]:
    """Return a page of merged audit rows for the store, plus the
    user-filter roster + the resolved page number. Pure read; no
    commit. Mirrors the legacy `admin_audit_log` route's logic:
        1) pull OperatorAuditLog + TransferAudit (cap at 500 each)
        2) apply target/action/user filters
        3) merge + sort by timestamp desc
        4) paginate
    """
    from api.Modules.Audit.Models import OperatorAuditLog, TransferAudit
    from api.Modules.Tenancy.Models import User

    op_q = db.query(OperatorAuditLog).filter_by(store_id=store_id)
    tx_q = db.query(TransferAudit).filter_by(store_id=store_id)

    if target_filter:
        op_q = op_q.filter_by(target_type=target_filter)
        if target_filter != "transfer":
            # TransferAudit is a transfer-only feed; suppress when
            # the operator picked a non-transfer target.
            from sqlalchemy import false
            tx_q = tx_q.filter(false())

    if user_filter:
        try:
            uid = int(user_filter)
            op_q = op_q.filter_by(user_id=uid)
            tx_q = tx_q.filter_by(user_id=uid)
        except ValueError:
            # Operator-supplied junk; treat as no filter rather than
            # leaking a 422 to the SPA. Mirrors legacy behavior.
            pass

    if action_filter:
        op_q = op_q.filter_by(action=action_filter)
        tx_q = tx_q.filter_by(action=action_filter)

    op_rows: list[Any] = (
        op_q.order_by(OperatorAuditLog.created_at.desc()).limit(500).all()
    )
    tx_rows: list[Any] = (
        tx_q.order_by(TransferAudit.created_at.desc()).limit(500).all()
    )

    user_ids = (
        {r.user_id for r in op_rows if r.user_id}
        | {r.user_id for r in tx_rows if r.user_id}
    )
    users = (
        {u.id: u for u in db.query(User).filter(User.id.in_(user_ids)).all()}
        if user_ids else {}
    )

    merged: list[dict[str, Any]] = []
    for r in op_rows:
        _u = users.get(r.user_id) if r.user_id else None
        merged.append({
            "ts":           r.created_at.isoformat() if r.created_at else "",
            "user_name":    r.user_name or (
                _u.username if _u is not None else ""
            ),
            "user_role":    r.user_role or "",
            "action":       r.action or "",
            "target_type":  r.target_type or "",
            "target_id":    r.target_id or "",
            "target_label": r.target_label or "",
            "summary":      r.summary or "",
            "source":       "operator",
        })
    for r in tx_rows:
        u = users.get(r.user_id) if r.user_id else None
        merged.append({
            "ts":           r.created_at.isoformat() if r.created_at else "",
            "user_name":    (
                (u.full_name or u.username) if u
                else (r.employee_name or "")
            ),
            "user_role":    u.role if u else "",
            "action":       r.action or "",
            "target_type":  "transfer",
            "target_id":    str(r.transfer_id),
            "target_label": (
                (r.summary[:80] if r.summary else f"Transfer #{r.transfer_id}")
            ),
            "summary":      r.summary or "",
            "source":       "transfer",
        })
    merged.sort(key=lambda x: x["ts"], reverse=True)

    total = len(merged)
    total_pages = max(1, (total + PER_PAGE - 1) // PER_PAGE)
    page = max(1, min(page, total_pages))
    start = (page - 1) * PER_PAGE
    page_rows = merged[start:start + PER_PAGE]

    store_users_raw = (
        db.query(User).filter_by(store_id=store_id)
          .order_by(User.full_name, User.username).all()
    )
    store_users = [
        {
            "id":    u.id,
            "label": u.full_name or u.username or "",
            "role":  u.role or "",
        }
        for u in store_users_raw
    ]

    return {
        "rows":         page_rows,
        "total":        total,
        "page":         page,
        "per_page":     PER_PAGE,
        "total_pages":  total_pages,
        "store_users":  store_users,
    }
