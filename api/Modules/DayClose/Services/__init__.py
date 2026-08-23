"""DayClose — Services.

Business rules for the generalized retail day-close. All money in
integer cents (P0-3); all writes leave commit to the Controller so
the audit row lands in the same transaction (CLAUDE.md invariant #7
pattern).

Write semantics mirror the lottery day-count: submitting a close
for a (store, date, register, shift) key that already exists
REPLACES it — Z-report re-keys are corrections, not history. The
audit trail records every submission.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from sqlalchemy.orm import Session

from api.Modules.DayClose.Models import (
    Department,
    DepartmentSale,
    RegisterClose,
)


class DayCloseError(Exception):
    """Base for day-close domain errors — Controllers map to 4xx."""


class DayCloseNotFoundError(DayCloseError):
    pass


class DayCloseStateError(DayCloseError):
    """Invalid write (message is user-safe)."""


# ── Departments ────────────────────────────────────────────


def list_departments(
    db: Session, store_id: int, include_inactive: bool = False,
) -> list[Department]:
    q = db.query(Department).filter_by(store_id=store_id)
    if not include_inactive:
        q = q.filter(Department.is_active == True)  # noqa: E712
    return q.order_by(Department.sort_order, Department.name).all()


def _department_name_taken(
    db: Session, store_id: int, name: str, exclude_id: int | None = None,
) -> bool:
    q = db.query(Department).filter(
        Department.store_id == store_id,
        Department.name.ilike(name),
    )
    if exclude_id is not None:
        q = q.filter(Department.id != exclude_id)
    return q.first() is not None


def create_department(
    db: Session, store_id: int, *, name: str, sort_order: int = 0,
) -> Department:
    if _department_name_taken(db, store_id, name):
        raise DayCloseStateError(
            f"A department named {name!r} already exists.",
        )
    dept = Department(store_id=store_id, name=name, sort_order=sort_order)
    db.add(dept)
    db.flush()
    return dept


def update_department(
    db: Session, store_id: int, department_id: int, *,
    name: str | None = None, sort_order: int | None = None,
    is_active: bool | None = None,
) -> Department:
    dept = db.get(Department, department_id)
    if dept is None or dept.store_id != store_id:
        raise DayCloseNotFoundError("Department not found")
    if name is not None:
        if _department_name_taken(db, store_id, name, exclude_id=dept.id):
            raise DayCloseStateError(
                f"A department named {name!r} already exists.",
            )
        dept.name = name
    if sort_order is not None:
        dept.sort_order = int(sort_order)
    if is_active is not None:
        dept.is_active = bool(is_active)
    db.flush()
    return dept


# ── Register closes ────────────────────────────────────────


def upsert_register_close(
    db: Session, store_id: int, day: date, *,
    register_label: str, shift_label: str = "",
    gross_sales: float, sales_tax: float, cash_total: float,
    card_total: float, other_total: float,
    cash_counted: float | None, notes: str = "",
    department_sales: dict[int, float] | None = None,
    created_by: int | None,
) -> RegisterClose:
    """Create or replace the close for one (register, shift) on one
    day. Department sales are replace-all: the submitted lines
    become the close's full breakdown."""
    if not register_label.strip():
        raise DayCloseStateError("Register label is required.")

    sales = department_sales or {}
    if sales:
        depts = {
            d.id: d
            for d in db.query(Department)
            .filter(
                Department.store_id == store_id,
                Department.id.in_(sales.keys()),
            )
            .all()
        }
        missing = set(sales.keys()) - set(depts.keys())
        if missing:
            raise DayCloseNotFoundError("Department not found")

    row = (
        db.query(RegisterClose)
        .filter_by(
            store_id=store_id, report_date=day,
            register_label=register_label.strip(),
            shift_label=shift_label.strip(),
        )
        .first()
    )
    if row is None:
        row = RegisterClose(
            store_id=store_id, report_date=day,
            register_label=register_label.strip(),
            shift_label=shift_label.strip(),
        )
        db.add(row)
    row.gross_sales = gross_sales
    row.sales_tax = sales_tax
    row.cash_total = cash_total
    row.card_total = card_total
    row.other_total = other_total
    row.cash_counted = cash_counted
    row.notes = notes.strip()
    row.created_by = created_by
    row.department_sales = [
        DepartmentSale(
            store_id=store_id, department_id=dept_id, amount=amount,
        )
        for dept_id, amount in sales.items()
    ]
    db.flush()
    return row


def delete_register_close(
    db: Session, store_id: int, close_id: int,
) -> RegisterClose:
    row = db.get(RegisterClose, close_id)
    if row is None or row.store_id != store_id:
        raise DayCloseNotFoundError("Register close not found")
    db.delete(row)
    db.flush()
    return row


# ── Day summary ────────────────────────────────────────────


@dataclass
class DepartmentDayTotal:
    department: Department
    amount_cents: int


@dataclass
class DayCloseSummary:
    closes: list[RegisterClose]
    department_totals: list[DepartmentDayTotal]
    gross_sales_cents: int
    sales_tax_cents: int
    cash_total_cents: int
    card_total_cents: int
    other_total_cents: int
    over_short_cents: int | None       # None until any drawer counted
    tender_variance_cents: int
    uncounted_drawers: int


def day_summary(db: Session, store_id: int, day: date) -> DayCloseSummary:
    """Every register close for the day + the day-level rollup.
    Department totals aggregate across closes; ``uncounted_drawers``
    flags closes whose drawer was never counted — the day-close
    equivalent of the lottery shrinkage nag."""
    closes = (
        db.query(RegisterClose)
        .filter_by(store_id=store_id, report_date=day)
        .order_by(RegisterClose.register_label, RegisterClose.shift_label)
        .all()
    )

    dept_totals: dict[int, DepartmentDayTotal] = {}
    gross = tax = cash = card = other = variance = 0
    over_short: int | None = None
    uncounted = 0
    for c in closes:
        gross += int(c.gross_sales_cents or 0)
        tax += int(c.sales_tax_cents or 0)
        cash += int(c.cash_total_cents or 0)
        card += int(c.card_total_cents or 0)
        other += int(c.other_total_cents or 0)
        variance += c.tender_variance_cents
        if c.over_short_cents is None:
            uncounted += 1
        else:
            over_short = (over_short or 0) + c.over_short_cents
        for line in c.department_sales:
            entry = dept_totals.get(line.department_id)
            if entry is None:
                dept_totals[line.department_id] = DepartmentDayTotal(
                    department=line.department,
                    amount_cents=int(line.amount_cents or 0),
                )
            else:
                entry.amount_cents += int(line.amount_cents or 0)

    ordered = sorted(
        dept_totals.values(),
        key=lambda t: (t.department.sort_order, t.department.name or ""),
    )
    return DayCloseSummary(
        closes=closes,
        department_totals=ordered,
        gross_sales_cents=gross,
        sales_tax_cents=tax,
        cash_total_cents=cash,
        card_total_cents=card,
        other_total_cents=other,
        over_short_cents=over_short,
        tender_variance_cents=variance,
        uncounted_drawers=uncounted,
    )


__all__ = [
    "DayCloseError", "DayCloseNotFoundError", "DayCloseStateError",
    "DayCloseSummary", "DepartmentDayTotal", "create_department",
    "day_summary", "delete_register_close", "list_departments",
    "update_department", "upsert_register_close",
]
