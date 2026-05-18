"""Paystub computation — gross pay for a roster member over a
date range, driven by approved time-clock entries × hourly rate.

Only ``approved`` entries count toward gross pay. Pending /
rejected rows are excluded — the admin uses the payroll list to
approve a shift before it shows up here. Open shifts (no
``clock_out_at``) are also excluded since their hours aren't
final.

This is the v1 paystub: hours, rate, gross pay, with the
underlying shifts itemized. Check-printing (MICR routing,
check-number sequence, signature line) is a separate item;
the operator hand-writes the check from this summary today.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from api.Modules.Tenancy.Models import StoreEmployee
from api.Modules.TimeClock.Models import TimeClockEntry


def compute_paystub(
    db: Session,
    *,
    store_id: int,
    store_employee_id: int,
    start: datetime,
    end: datetime,
) -> dict[str, Any]:
    """Return the paystub payload for the picked roster member
    over [start, end).

    Raises ``ValueError`` when the roster member doesn't belong
    to the store (cross-tenant probe).

    Shape:
      {
        "store_employee_id": int,
        "employee_name":     str,
        "hourly_rate":       float,
        "approved_hours":    float,
        "gross_pay":         float,
        "from_date":         "YYYY-MM-DD",
        "to_date":           "YYYY-MM-DD",
        "shifts": [
          {"clock_in_at": iso, "clock_out_at": iso,
           "hours_worked": float, "status": str, "notes": str},
          ...
        ],
      }
    """
    emp = db.get(StoreEmployee, store_employee_id)
    if emp is None or emp.store_id != store_id:
        raise ValueError(
            "That roster member doesn't belong to this store.",
        )

    rows = (
        db.query(TimeClockEntry)
          .filter(
              TimeClockEntry.store_id == store_id,
              TimeClockEntry.store_employee_id == store_employee_id,
              TimeClockEntry.clock_in_at >= start,
              TimeClockEntry.clock_in_at < end,
          )
          .order_by(TimeClockEntry.clock_in_at.asc())
          .all()
    )

    rate = float(emp.hourly_rate or 0.0)
    approved_hours = round(
        sum(
            (r.hours_worked or 0.0)
            for r in rows
            if r.status == "approved" and r.clock_out_at is not None
        ),
        4,
    )
    gross_pay = round(approved_hours * rate, 2)

    return {
        "store_employee_id": store_employee_id,
        "employee_name":     emp.name,
        "hourly_rate":       round(rate, 4),
        "approved_hours":    approved_hours,
        "gross_pay":         gross_pay,
        "from_date":         start.date().isoformat(),
        "to_date":           end.date().isoformat(),
        "shifts": [
            {
                "id":           r.id,
                "clock_in_at":
                    r.clock_in_at.isoformat() if r.clock_in_at else "",
                "clock_out_at":
                    r.clock_out_at.isoformat() if r.clock_out_at else None,
                "hours_worked": r.hours_worked,
                "status":       r.status or "pending",
                "notes":        r.notes or "",
            }
            for r in rows
        ],
    }
