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
from typing import Any
from api.Core.Clock import utc_now


router = APIRouter()


def _day_close_snapshot(
    db: Session, store_id: int, today: date,
) -> dict[str, Any] | None:
    """Latest day-close rollup for the module section. Prefers
    today; falls back to the most recent booked business day so
    the card shows real numbers first thing in the morning."""
    from api.Modules.DayClose.Models import RegisterClose
    from api.Modules.DayClose.Services import day_summary

    target = today
    if not (
        db.query(RegisterClose.id)
        .filter_by(store_id=store_id, report_date=today).first()
    ):
        latest = (
            db.query(RegisterClose.report_date)
            .filter_by(store_id=store_id)
            .order_by(RegisterClose.report_date.desc())
            .first()
        )
        if latest is None:
            return None
        target = latest[0]
    summary = day_summary(db, store_id, target)
    return {
        "date": target.isoformat(),
        "gross_sales": summary.gross_sales_cents / 100.0,
        "sales_tax": summary.sales_tax_cents / 100.0,
        "over_short": (
            None if summary.over_short_cents is None
            else summary.over_short_cents / 100.0
        ),
        "uncounted_drawers": summary.uncounted_drawers,
        "closes": len(summary.closes),
        "top_departments": [
            {
                "name": t.department.name or "",
                "amount": t.amount_cents / 100.0,
            }
            for t in summary.department_totals[:5]
        ],
    }


def _lottery_snapshot(
    db: Session, store_id: int, today: date,
) -> dict[str, Any] | None:
    """Latest lottery day-close rollup. Prefers today; falls back
    to the most recent counted day. None until the store has any
    active packs or counts."""
    from api.Modules.Lottery.Models import LotteryDayCount, LotteryPack
    from api.Modules.Lottery.Services import day_summary as lottery_day

    active_packs = (
        db.query(LotteryPack)
        .filter_by(store_id=store_id, status="active").count()
    )
    target = today
    if not (
        db.query(LotteryDayCount.id)
        .filter_by(store_id=store_id, report_date=today).first()
    ):
        latest = (
            db.query(LotteryDayCount.report_date)
            .filter_by(store_id=store_id)
            .order_by(LotteryDayCount.report_date.desc())
            .first()
        )
        if latest is None and active_packs == 0:
            return None
        if latest is not None:
            target = latest[0]
    summary = lottery_day(db, store_id, target)
    return {
        "date": target.isoformat(),
        "tickets_sold": summary.total_sold,
        "value": summary.total_value_cents / 100.0,
        "uncounted_active_packs": summary.uncounted_active_packs,
        "active_packs": active_packs,
    }


def _sales_block(
    db: Session, store_id: int, today: date,
) -> dict[str, Any]:
    """Store-sales rollup from day-close register totals (D-1,
    generic store dashboard). All sums in dollars. ``trend`` is
    the last 14 calendar days, zero-filled, oldest first — feeds
    the daily-sales line chart."""
    from datetime import timedelta

    from sqlalchemy import func

    from api.Modules.DayClose.Models import RegisterClose

    def _sum_between(start: date, end: date) -> float:
        cents = (
            db.query(func.coalesce(
                func.sum(RegisterClose.gross_sales_cents), 0,
            ))
            .filter(
                RegisterClose.store_id == store_id,
                RegisterClose.report_date >= start,
                RegisterClose.report_date <= end,
            )
            .scalar()
        )
        return float(cents or 0) / 100.0

    month_start = date(today.year, today.month, 1)
    trend_start = today - timedelta(days=13)
    rows = (
        db.query(
            RegisterClose.report_date,
            func.coalesce(func.sum(RegisterClose.gross_sales_cents), 0),
        )
        .filter(
            RegisterClose.store_id == store_id,
            RegisterClose.report_date >= trend_start,
            RegisterClose.report_date <= today,
        )
        .group_by(RegisterClose.report_date)
        .all()
    )
    by_day = {r[0]: float(r[1] or 0) / 100.0 for r in rows}
    trend = [
        {
            "date": (trend_start + timedelta(days=i)).isoformat(),
            "amount": by_day.get(trend_start + timedelta(days=i), 0.0),
        }
        for i in range(14)
    ]
    return {
        "today": _sum_between(today, today),
        "yesterday": _sum_between(
            today - timedelta(days=1), today - timedelta(days=1),
        ),
        "month_to_date": _sum_between(month_start, today),
        "d7": _sum_between(today - timedelta(days=6), today),
        "d15": _sum_between(today - timedelta(days=14), today),
        "d30": _sum_between(today - timedelta(days=29), today),
        "trend": trend,
        "hourly": _hourly_block(db, store_id),
    }


def _hourly_block(db: Session, store_id: int) -> dict[str, Any] | None:
    """Hourly-sales chart data (G-3): the two most recent business
    days with hour buckets — "current" is live for an in-progress
    day (the Gilbarco agent increments buckets per transaction).
    None until the store has any hourly data."""
    from api.Modules.DayClose.Models import HourlySale

    dates = [
        d for (d,) in db.query(HourlySale.report_date)
        .filter_by(store_id=store_id)
        .distinct()
        .order_by(HourlySale.report_date.desc())
        .limit(2)
        .all()
    ]
    if not dates:
        return None
    rows = (
        db.query(HourlySale)
        .filter(
            HourlySale.store_id == store_id,
            HourlySale.report_date.in_(dates),
        )
        .all()
    )

    def _series(day: date) -> list[float]:
        arr = [0.0] * 24
        for r in rows:
            if r.report_date == day and 0 <= int(r.hour) <= 23:
                arr[int(r.hour)] += float(r.amount_cents or 0) / 100.0
        return arr

    current, previous = dates[0], (dates[1] if len(dates) > 1 else None)
    cur = _series(current)
    prev = _series(previous) if previous else None
    return {
        "current_date": current.isoformat(),
        "previous_date": previous.isoformat() if previous else None,
        "current": cur,
        "previous": prev,
        "current_total": round(sum(cur), 2),
        "previous_total": round(sum(prev), 2) if prev else None,
    }


def _purchases_block(
    db: Session, store_id: int, today: date,
) -> dict[str, Any]:
    """Purchase-invoice rollup (module_price_book). Totals are the
    derived subtotal + tax + other, summed in SQL."""
    from datetime import timedelta

    from sqlalchemy import func

    from api.Modules.Catalog.Models import PurchaseInvoice

    total_expr = func.coalesce(func.sum(
        PurchaseInvoice.subtotal_cents
        + PurchaseInvoice.tax_cents
        + PurchaseInvoice.other_cents,
    ), 0)

    def _sum_since(start: date) -> float:
        cents = (
            db.query(total_expr)
            .filter(
                PurchaseInvoice.store_id == store_id,
                PurchaseInvoice.invoice_date >= start,
                PurchaseInvoice.invoice_date <= today,
            )
            .scalar()
        )
        return float(cents or 0) / 100.0

    open_q = (
        db.query(func.count(PurchaseInvoice.id), total_expr)
        .filter(
            PurchaseInvoice.store_id == store_id,
            PurchaseInvoice.status == "open",
        )
        .one()
    )
    return {
        "today": _sum_since(today),
        "d7": _sum_since(today - timedelta(days=6)),
        "d15": _sum_since(today - timedelta(days=14)),
        "d30": _sum_since(today - timedelta(days=29)),
        "open_count": int(open_q[0] or 0),
        "open_total": float(open_q[1] or 0) / 100.0,
    }


def _clocked_in_block(db: Session, store_id: int) -> list[dict[str, Any]]:
    """Who is on the clock right now — open TimeClockEntry rows
    (clock_out_at IS NULL) joined to the roster for names."""
    from api.Modules.Tenancy.Models import StoreEmployee
    from api.Modules.TimeClock.Models import TimeClockEntry

    rows = (
        db.query(TimeClockEntry, StoreEmployee)
        .join(
            StoreEmployee,
            StoreEmployee.id == TimeClockEntry.store_employee_id,
        )
        .filter(
            TimeClockEntry.store_id == store_id,
            TimeClockEntry.clock_out_at.is_(None),
        )
        .order_by(TimeClockEntry.clock_in_at)
        .all()
    )
    return [
        {
            "name": emp.name or "",
            "clock_in_at": (
                entry.clock_in_at.isoformat()
                if entry.clock_in_at else None
            ),
        }
        for entry, emp in rows
    ]


def _admin_summary(db: Session, store_id: int) -> dict[str, Any]:
    from api.Modules.BankSync.Models import StripeBankAccount
    from api.Modules.Batches.Models import ACHBatch
    from api.Modules.Billing.Services.feature_flags import (
        enabled_module_flags,
    )
    from api.Modules.DailyBook.Models import DailyReport
    from api.Modules.Monthly.Models import MonthlyFinancial
    from api.Modules.Tenancy.Models import Store
    from api.Modules.Owners.Services import OWNER_TRANSFER_EXCLUDED
    from api.Modules.Transfers.Models import Transfer
    from api.Modules.Transfers.Services import store_mt_companies
    today = date.today()
    month_start = date(today.year, today.month, 1)

    store = db.get(Store, store_id)
    if store is None:
        raise HTTPException(status_code=404, detail="Store not found.")

    # The dashboard is module-driven (P1-10): each enabled module
    # contributes its section; disabled modules cost zero queries.
    modules = enabled_module_flags(db, store)
    money_services = "module_money_services" in modules

    total_transfers = today_transfers = pending_ach = 0
    recent_transfers: list[Any] = []
    recent_batches: list[Any] = []
    company_stats: list[dict[str, Any]] = []
    if money_services:
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
            func.coalesce(func.sum(Transfer.send_amount_cents), 0) / 100.0,
            func.coalesce(func.sum(Transfer.fee_cents), 0) / 100.0,
        ).filter(
            Transfer.store_id == store_id,
            Transfer.send_date >= month_start,
            Transfer.status.notin_(OWNER_TRANSFER_EXCLUDED),
        ).group_by(Transfer.company).all())
        co_by_name = {co: (int(c or 0), float(t or 0), float(f or 0))
                      for co, c, t, f in co_q}
        for co in store_mt_companies(store):
            count, total, fees = co_by_name.get(co, (0, 0.0, 0.0))
            company_stats.append({
                "company": co, "count": count, "total": total,
                "fees": fees,
            })

    day_close = (
        _day_close_snapshot(db, store_id, today)
        if "module_day_close" in modules else None
    )
    lottery = (
        _lottery_snapshot(db, store_id, today)
        if "module_lottery" in modules else None
    )

    # Generic store blocks (D-1): sales-first dashboard. Each block
    # renders only when its module is on; clocked-in is universal
    # (the time clock isn't module-gated).
    sales = (
        _sales_block(db, store_id, today)
        if "module_day_close" in modules else None
    )
    purchases = (
        _purchases_block(db, store_id, today)
        if "module_price_book" in modules else None
    )
    clocked_in = _clocked_in_block(db, store_id)

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
        "modules": modules,
        "day_close": day_close,
        "lottery": lottery,
        "sales": sales,
        "purchases": purchases,
        "clocked_in": clocked_in,
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


def _employee_summary(db: Session, store_id: int) -> dict[str, Any]:
    from api.Modules.Billing.Services.feature_flags import (
        enabled_module_flags,
    )
    from api.Modules.Tenancy.Models import Store
    from api.Modules.Transfers.Models import Transfer
    today = date.today()
    store = db.get(Store, store_id)
    modules = enabled_module_flags(db, store)
    rows = []
    if "module_money_services" in modules:
        rows = (
            db.query(Transfer)
            .filter_by(store_id=store_id, send_date=today)
            .order_by(Transfer.created_at.desc()).all()
        )
    return {
        "today": today.isoformat(),
        "modules": modules,
        "day_close": (
            _day_close_snapshot(db, store_id, today)
            if "module_day_close" in modules else None
        ),
        "lottery": (
            _lottery_snapshot(db, store_id, today)
            if "module_lottery" in modules else None
        ),
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


def _superadmin_summary(db: Session) -> dict[str, Any]:
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
    claims: dict[str, Any] = Depends(get_principal),
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
    claims: dict[str, Any] = Depends(get_principal),
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
    now = utc_now()
    start = now - timedelta(days=days)
    return compute_peak_hours(
        db, store_id=int(store_id), start=start, end=now,
    )
