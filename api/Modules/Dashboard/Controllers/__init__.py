"""Dashboard module — Controllers (FastAPI router).

Mounts at `/api/v2/dashboard/*`. Single read-only endpoint:

    GET /dashboard/summary  → role-shaped landing payload

The payload branches on the caller's JWT role:

  - admin    → KPIs, company-of-month rollup, recent transfers/
               batches, bank-account peek, today/this-month report
               status.
  - employee → today's transfers + same-day totals.
  - superadmin → platform-wide BI (delegates to the existing
                 superadmin_dashboard_context Service).

No new aggregation logic is invented here — the route reads from
the same models the legacy Flask `/dashboard` view used.
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
    from app import store_mt_companies
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
    """Delegate to the existing service. Map ORM rows + datetimes
    into JSON-native primitives so FastAPI's encoder can serialise
    without a custom encoder."""
    from api.Modules.Superadmin.Services.dashboard import (
        superadmin_dashboard_context,
    )
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

    return {k: _safe(v) for k, v in ctx.items()}


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
