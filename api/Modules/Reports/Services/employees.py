"""Employee-driven services.

Two services with deliberately different group keys (per the ADR):

  sales_by_employee     — Group by `Transfer.created_by`. Answers
                          "which login user authored the most rows?"
                          Useful for audit / per-account attribution.

  cashier_productivity  — Group by `Transfer.employee_id`. Answers
                          "which cashier on duty handled the most
                          customers?" The two answers diverge when
                          one admin logs transfers on behalf of
                          multiple cashiers.

Both resolve their FKs to display names. Cashier flavor adds an
`is_active` flag so the template can tag deactivated roster rows.
"""
from typing import Iterable

from sqlalchemy.orm import Session

from api.Modules.Reports.Models import StoreEmployee, Transfer, User
from api.Modules.Reports.Repositories.transfers import aggregate


def sales_by_employee(
    db: Session, store_ids: Iterable[int], d_from, d_to,
) -> tuple[list[dict], dict]:
    """Group by `Transfer.created_by`, resolve to User display names.

    Transfers with no `created_by` are bucketed as `"(unattributed)"`
    so legacy rows don't disappear from the totals.
    """
    rows, totals = aggregate(db, store_ids, d_from, d_to, Transfer.created_by)
    user_ids = [r["key"] for r in rows if r["key"] is not None]
    users = (
        {u.id: u for u in db.query(User).filter(User.id.in_(user_ids)).all()}
        if user_ids else {}
    )
    for r in rows:
        uid = r.pop("key")
        if uid is None:
            r["employee"] = "(unattributed)"
            r["username"] = ""
        else:
            u = users.get(uid)
            r["employee"] = (u.full_name or u.username) if u else f"User #{uid}"
            r["username"] = u.username if u else ""
    rows.sort(key=lambda r: r["sent"], reverse=True)
    return rows, totals


def cashier_productivity(
    db: Session, store_ids: Iterable[int], d_from, d_to,
) -> tuple[list[dict], dict]:
    """Group by `Transfer.employee_id` (the cashier on duty), resolve
    to `StoreEmployee` roster rows.

    Sorted by transfer count desc — the busiest cashier floats to
    the top, which is what the typical operator's question is when
    they hit this report.
    """
    rows, totals = aggregate(db, store_ids, d_from, d_to, Transfer.employee_id)
    employee_ids = [r["key"] for r in rows if r["key"] is not None]
    employees = (
        {e.id: e for e in
         db.query(StoreEmployee).filter(StoreEmployee.id.in_(employee_ids)).all()}
        if employee_ids else {}
    )
    for r in rows:
        eid = r.pop("key")
        if eid is None:
            r["cashier"] = "(unattributed)"
            r["is_active"] = False
        else:
            e = employees.get(eid)
            if e:
                r["cashier"] = e.name
                r["is_active"] = bool(e.is_active)
            else:
                r["cashier"] = f"Cashier #{eid}"
                r["is_active"] = False
    rows.sort(key=lambda r: r["count"], reverse=True)
    return rows, totals
