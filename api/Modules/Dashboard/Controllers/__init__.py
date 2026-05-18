"""Dashboard module — Controllers (FastAPI router).

Mounts at `/api/v2/dashboard/*`. Single read-only endpoint:

    GET /dashboard/summary  → role-shaped landing payload

The payload branches on the caller's JWT role:

  - admin    → KPIs, company-of-month rollup, recent transfers/
               batches, bank-account peek, today/this-month report
               status.
  - employee → today's transfers + same-day totals.
  - superadmin → platform-wide BI (delegates to
                 ``superadmin_dashboard_context``).
"""
from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from api.Core.Database import get_db
from api.Modules.Auth.Controllers import get_principal


router = APIRouter()


def _admin_summary(db: Session, store_id: int) -> dict:
    from api.Modules.BankSync.Models import StripeBankAccount
    from api.Modules.Batches.Models import ACHBatch
    from api.Modules.DailyBook.Models import DailyReport
    from api.Modules.Monthly.Models import MonthlyFinancial
    from api.Modules.Tenancy.Models import Store
    from api.Modules.Transfers.Models import Transfer
    from api.Modules.Transfers.Services import store_mt_companies
    today = date.today()
    month_start = date(today.year, today.month, 1)

    store = db.get(Store, store_id)
    if store is None:
        raise HTTPException(status_code=404, detail="Store not found.")

    total_transfers = (
        db.query(Transfer).filter_by(store_id=store_id).count()
    )
    today_transfers = (
        db.query(Transfer)
        .filter_by(store_id=store_id, send_date=today).count()
    )
    pending_ach = (
        db.query(ACHBatch)
        .filter_by(store_id=store_id, reconciled=False).count()
    )

    recent_transfers = (
        db.query(Transfer).filter_by(store_id=store_id)
        .order_by(Transfer.created_at.desc()).limit(8).all()
    )
    recent_batches = (
        db.query(ACHBatch).filter_by(store_id=store_id)
        .order_by(ACHBatch.ach_date.desc()).limit(5).all()
    )

    from sqlalchemy import func
    co_q = (db.query(
        Transfer.company,
        func.count(Transfer.id),
        func.coalesce(func.sum(Transfer.send_amount), 0.0),
        func.coalesce(func.sum(Transfer.fee), 0.0),
    ).filter(
        Transfer.store_id == store_id,
        Transfer.send_date >= month_start,
        Transfer.status.notin_(["Canceled", "Rejected"]),
    ).group_by(Transfer.company).all())
    co_by_name = {co: (int(c or 0), float(t or 0), float(f or 0))
                  for co, c, t, f in co_q}
    company_stats = []
    for co in store_mt_companies(store):
        count, total, fees = co_by_name.get(co, (0, 0.0, 0.0))
        company_stats.append({
            "company": co, "count": count, "total": total, "fees": fees,
        })

    today_report = (
        db.query(DailyReport)
        .filter_by(store_id=store_id, report_date=today).first()
    )
    month_report = (
        db.query(MonthlyFinancial).filter_by(
            store_id=store_id, year=today.year, month=today.month,
        ).first()
    )
    stripe_accounts = (
        db.query(StripeBankAccount)
        .filter_by(store_id=store_id, enabled=True)
        .order_by(StripeBankAccount.connected_at.desc()).limit(3).all()
    )

    return {
        "today": today.isoformat(),
        "kpis": {
            "total_transfers": total_transfers,
            "today_transfers": today_transfers,
            "pending_ach": pending_ach,
            "today_report_entered": today_report is not None,
            "net_income_month": (
                float(month_report.net_income) if month_report else None
            ),
        },
        "company_stats": company_stats,
        "recent_transfers": [
            {
                "id": t.id, "send_date": t.send_date.isoformat(),
                "sender_name": t.sender_name, "company": t.company,
                "send_amount": float(t.send_amount or 0),
                "status": t.status,
            }
            for t in recent_transfers
        ],
        "recent_batches": [
            {
                "id": b.id, "ach_date": b.ach_date.isoformat(),
                "company": b.company,
                "ach_amount": float(b.ach_amount or 0),
                "variance": float(b.variance or 0),
                "status": b.status,
            }
            for b in recent_batches
        ],
        "stripe_accounts": [
            {
                "id": a.id,
                "display_name": a.display_name,
                "institution_name": a.institution_name,
                "last4": a.last4,
                "last_balance": float(a.last_balance or 0),
                "last_balance_as_of": (
                    a.last_balance_as_of.isoformat()
                    if a.last_balance_as_of else None
                ),
            }
            for a in stripe_accounts
        ],
    }


def _employee_summary(db: Session, store_id: int) -> dict:
    from api.Modules.Transfers.Models import Transfer
    today = date.today()
    rows = (
        db.query(Transfer)
        .filter_by(store_id=store_id, send_date=today)
        .order_by(Transfer.created_at.desc()).all()
    )
    return {
        "today": today.isoformat(),
        "today_transfers": [
            {
                "id": t.id,
                "created_at": (
                    t.created_at.isoformat() if t.created_at else None
                ),
                "sender_name": t.sender_name,
                "company": t.company,
                "send_amount": float(t.send_amount or 0),
                "fee": float(t.fee or 0),
                "recipient_name": t.recipient_name,
                "country": t.country,
                "confirm_number": t.confirm_number,
                "status": t.status,
            }
            for t in rows
        ],
        "totals": {
            "sent": sum(float(t.send_amount or 0) for t in rows),
            "fees": sum(float(t.fee or 0) for t in rows),
            "count": len(rows),
        },
    }


def _superadmin_summary(db: Session) -> dict:
    """Delegate to the existing service. Two responsibilities:

      1. Map ORM rows + datetimes into JSON-native primitives so
         FastAPI's encoder can serialise without a custom encoder.
      2. Adapt the legacy ``*_count`` / ``estimated_mrr`` field
         names that ``superadmin_dashboard_context`` returns to
         the ``*_stores`` / ``mrr_total`` shape the SPA expects.
         Without the adapter the platform KPI tiles render as
         "—" because the SPA reads keys that don't exist in the
         response.
    """
    from datetime import datetime as _dt
    from api.Modules.Superadmin.Services.dashboard import (
        superadmin_dashboard_context,
    )
    from api.Modules.Tenancy.Models import Store

    ctx = superadmin_dashboard_context(db)

    def _safe(v):
        if isinstance(v, (datetime, date)):
            return v.isoformat()
        if isinstance(v, dict):
            return {k: _safe(x) for k, x in v.items()}
        if isinstance(v, list):
            return [_safe(x) for x in v]
        if hasattr(v, "__table__"):
            return {c.name: _safe(getattr(v, c.name))
                    for c in v.__table__.columns}
        return v

    out = {k: _safe(v) for k, v in ctx.items()}

    # SPA-facing aliases. Don't drop the original ``*_count`` keys —
    # any internal Python consumer keeps working — just publish the
    # ``*_stores`` shape the React SuperadminControls + Dashboard
    # routes read.
    if "active_count" in out:
        out.setdefault("active_stores", out["active_count"])
    if "trial_count" in out:
        out.setdefault("trial_stores", out["trial_count"])
    if "paid_count" in out:
        out.setdefault("paid_stores", out["paid_count"])
    if "inactive_count" in out:
        out.setdefault("inactive_stores", out["inactive_count"])
    if "estimated_mrr" in out:
        mrr = out["estimated_mrr"]
        out.setdefault("mrr_total", mrr)
        if isinstance(mrr, (int, float)):
            # ARR = MRR × 12. Cheap derived value the SPA shows
            # next to MRR on the Platform Controls overview.
            out.setdefault("arr_total", float(mrr) * 12.0)
    if "churn_30d" in out:
        out.setdefault("cancellations_30d", out["churn_30d"])

    # Retention queue: stores past cancellation, still inside the
    # 180-day data-retention window. Counted live so the KPI tile
    # always reflects current state (no separate flag to keep in
    # sync).
    now = _dt.utcnow()
    out.setdefault(
        "retention_queue",
        db.query(Store)
          .filter(
              Store.data_retention_until.isnot(None),
              Store.data_retention_until > now,
          )
          .count(),
    )
    return out


@router.get("/summary")
def dashboard_summary(
    db: Session = Depends(get_db),
    claims: dict = Depends(get_principal),
):
    """Role-shaped landing payload for /app/dashboard.

    Returns `{role, ...payload}` so the SPA can branch on `role`
    and render the matching component without a second round-trip.
    """
    role = claims.get("role")
    if role == "superadmin":
        return {"role": "superadmin", **_superadmin_summary(db)}
    store_id = claims.get("store_id")
    if not store_id:
        raise HTTPException(
            status_code=400,
            detail="No store context — owners use /api/v2/owner/*.",
        )
    if role == "admin":
        return {"role": "admin", **_admin_summary(db, int(store_id))}
    if role == "employee":
        return {"role": "employee", **_employee_summary(db, int(store_id))}
    raise HTTPException(
        status_code=403,
        detail=f"Dashboard not available for role={role!r}.",
    )


@router.get("/peak-hours")
def dashboard_peak_hours(
    days: int = 30,
    db: Session = Depends(get_db),
    claims: dict = Depends(get_principal),
):
    """7×24 heatmap of transfer activity over the last ``days``
    days (default 30). Bucketed by weekday × hour-of-day in
    the store's local timezone — feeds the dashboard heatmap
    card.

    Admin / employee roles tied to a single store. Owners and
    superadmin without a store_id get 400 (they aggregate
    across umbrellas via /owner/* instead).
    """
    role = claims.get("role")
    store_id = claims.get("store_id")
    if not store_id:
        raise HTTPException(
            status_code=400,
            detail="No store context — owners use /api/v2/owner/*.",
        )
    if role not in ("admin", "employee", "owner", "superadmin"):
        raise HTTPException(status_code=403, detail="Role not allowed.")
    if days < 1 or days > 365:
        raise HTTPException(
            status_code=422,
            detail="``days`` must be between 1 and 365.",
        )
    from api.Modules.Dashboard.Services import compute_peak_hours
    from datetime import timedelta
    now = datetime.utcnow()
    start = now - timedelta(days=days)
    return compute_peak_hours(
        db, store_id=int(store_id), start=start, end=now,
    )
