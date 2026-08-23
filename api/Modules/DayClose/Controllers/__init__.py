"""DayClose module — Controllers (FastAPI router).

Mounts at `/api/v2/dayclose/*`:

  GET    /departments              list departments (?include_inactive=1)
  POST   /departments              create department
  PUT    /departments/{id}         rename / reorder / deactivate
  GET    /day/{date}               day summary (closes + dept rollup)
  POST   /day/{date}/closes        upsert one register/shift close
                                   (replaces on the same register +
                                   shift key; dept lines replace-all)
  DELETE /closes/{id}              remove a close (admin)

Cashiers (employees) hold day_close.create/read so they can submit
their own shift close; department catalog + deletions need admin
update rights. Every mutation records an operator-audit row
(invariant #7).
"""
from datetime import date, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from sqlalchemy.orm import Session

from api.Core.Database import get_db
from api.Core.Money import to_dollars
from api.Modules.Auth.Controllers import get_principal
from api.Modules.Auth.Services.principal import (
    require_permission,
    resolve_store_scope,
)
from api.Modules.DayClose.Models import Department, RegisterClose
from api.Modules.DayClose.Requests import (
    DayCloseSummaryResponse,
    DepartmentListResponse,
    DepartmentResponse,
    DepartmentRow,
    DepartmentSaleRow,
    DepartmentTotalRow,
    DepartmentUpdateRequest,
    DepartmentWriteRequest,
    RegisterCloseRow,
    RegisterCloseWriteRequest,
)
from api.Modules.DayClose.Services import (
    DayCloseNotFoundError,
    DayCloseStateError,
    create_department,
    day_summary,
    delete_register_close,
    list_departments,
    update_department,
    upsert_register_close,
)

router = APIRouter(prefix="/dayclose", tags=["dayclose"])


def _audit(
    db: Session, *, claims: dict[str, Any], action: str,
    target_type: str, target_id: str, summary: str,
) -> None:
    """Operator-audit emitter — CLAUDE.md invariant #7."""
    from api.Modules.Audit.Services import record_operator_action
    record_operator_action(
        db,
        store_id=int(claims["store_id"]),
        user_id=int(claims["sub"]),
        user_name=claims.get("name") or claims.get("username") or "",
        user_role=claims.get("role") or "",
        target_type=target_type,
        action=action,
        target_id=target_id,
        summary=summary[:255],
    )


def _parse_date(raw: str, field: str) -> date:
    try:
        return datetime.strptime(raw, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(
            status_code=422,
            detail={"field": field, "message": "Use YYYY-MM-DD."},
        )


def _department_row(d: Department) -> DepartmentRow:
    return DepartmentRow(
        id=d.id, name=d.name or "",
        sort_order=int(d.sort_order or 0),
        is_active=bool(d.is_active),
    )


def _close_row(c: RegisterClose) -> RegisterCloseRow:
    return RegisterCloseRow(
        id=c.id,
        register_label=c.register_label or "",
        shift_label=c.shift_label or "",
        gross_sales=c.gross_sales,
        sales_tax=c.sales_tax,
        cash_total=c.cash_total,
        card_total=c.card_total,
        other_total=c.other_total,
        cash_counted=c.cash_counted,
        over_short=(
            None if c.over_short_cents is None
            else to_dollars(c.over_short_cents)
        ),
        tender_variance=to_dollars(c.tender_variance_cents),
        notes=c.notes or "",
        department_sales=[
            DepartmentSaleRow(
                department_id=line.department_id,
                department_name=line.department.name or "",
                amount=line.amount,
            )
            for line in sorted(
                c.department_sales,
                key=lambda l: (
                    l.department.sort_order, l.department.name or "",
                ),
            )
        ],
    )


# ── Departments ────────────────────────────────────────────


@router.get("/departments", response_model=DepartmentListResponse)
def list_departments_route(
    include_inactive: bool = Query(False),
    db: Session = Depends(get_db),
    claims: dict[str, Any] = Depends(get_principal),
) -> DepartmentListResponse:
    sid = resolve_store_scope(claims)
    require_permission(claims, "day_close", "read")
    return DepartmentListResponse(
        departments=[_department_row(d) for d in list_departments(
            db, sid, include_inactive=include_inactive,
        )],
    )


@router.post("/departments", response_model=DepartmentResponse, status_code=201)
def create_department_route(
    body: DepartmentWriteRequest,
    db: Session = Depends(get_db),
    claims: dict[str, Any] = Depends(get_principal),
) -> DepartmentResponse:
    sid = resolve_store_scope(claims)
    require_permission(claims, "day_close", "update")
    try:
        dept = create_department(
            db, sid, name=body.name.strip(), sort_order=body.sort_order,
        )
    except DayCloseStateError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    _audit(
        db, claims=claims, action="create_department",
        target_type="department", target_id=str(dept.id),
        summary=f"department {dept.name}",
    )
    db.commit()
    return DepartmentResponse(department=_department_row(dept))


@router.put("/departments/{department_id}", response_model=DepartmentResponse)
def update_department_route(
    department_id: int = Path(..., ge=1),
    body: DepartmentUpdateRequest = ...,
    db: Session = Depends(get_db),
    claims: dict[str, Any] = Depends(get_principal),
) -> DepartmentResponse:
    sid = resolve_store_scope(claims)
    require_permission(claims, "day_close", "update")
    try:
        dept = update_department(
            db, sid, department_id,
            name=body.name.strip() if body.name is not None else None,
            sort_order=body.sort_order,
            is_active=body.is_active,
        )
    except DayCloseNotFoundError:
        raise HTTPException(status_code=404, detail="Department not found")
    except DayCloseStateError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    _audit(
        db, claims=claims, action="update_department",
        target_type="department", target_id=str(dept.id),
        summary=f"department {dept.name} updated",
    )
    db.commit()
    return DepartmentResponse(department=_department_row(dept))


# ── Day close ──────────────────────────────────────────────


def _summary_response(
    db: Session, sid: int, day: date,
) -> DayCloseSummaryResponse:
    summary = day_summary(db, sid, day)
    return DayCloseSummaryResponse(
        date=day.isoformat(),
        closes=[_close_row(c) for c in summary.closes],
        department_totals=[
            DepartmentTotalRow(
                department_id=t.department.id,
                department_name=t.department.name or "",
                amount=to_dollars(t.amount_cents),
            )
            for t in summary.department_totals
        ],
        gross_sales=to_dollars(summary.gross_sales_cents),
        sales_tax=to_dollars(summary.sales_tax_cents),
        cash_total=to_dollars(summary.cash_total_cents),
        card_total=to_dollars(summary.card_total_cents),
        other_total=to_dollars(summary.other_total_cents),
        over_short=(
            None if summary.over_short_cents is None
            else to_dollars(summary.over_short_cents)
        ),
        tender_variance=to_dollars(summary.tender_variance_cents),
        uncounted_drawers=summary.uncounted_drawers,
    )


@router.get("/day/{day}", response_model=DayCloseSummaryResponse)
def day_summary_route(
    day: str = Path(..., min_length=10, max_length=10),
    db: Session = Depends(get_db),
    claims: dict[str, Any] = Depends(get_principal),
) -> DayCloseSummaryResponse:
    sid = resolve_store_scope(claims)
    require_permission(claims, "day_close", "read")
    return _summary_response(db, sid, _parse_date(day, "day"))


@router.post("/day/{day}/closes", response_model=DayCloseSummaryResponse)
def upsert_close_route(
    day: str = Path(..., min_length=10, max_length=10),
    body: RegisterCloseWriteRequest = ...,
    db: Session = Depends(get_db),
    claims: dict[str, Any] = Depends(get_principal),
) -> DayCloseSummaryResponse:
    sid = resolve_store_scope(claims)
    require_permission(claims, "day_close", "create")
    d = _parse_date(day, "day")
    lines = {l.department_id: l.amount for l in body.department_sales}
    if len(lines) != len(body.department_sales):
        raise HTTPException(
            status_code=422,
            detail="Each department may appear only once.",
        )
    try:
        row = upsert_register_close(
            db, sid, d,
            register_label=body.register_label,
            shift_label=body.shift_label,
            gross_sales=body.gross_sales,
            sales_tax=body.sales_tax,
            cash_total=body.cash_total,
            card_total=body.card_total,
            other_total=body.other_total,
            cash_counted=body.cash_counted,
            notes=body.notes,
            department_sales=lines,
            created_by=int(claims["sub"]),
        )
    except DayCloseNotFoundError:
        raise HTTPException(status_code=404, detail="Department not found")
    except DayCloseStateError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    _audit(
        db, claims=claims, action="upsert_register_close",
        target_type="register_close", target_id=str(row.id),
        summary=f"{d.isoformat()} {row.register_label}"
                f"{' / ' + row.shift_label if row.shift_label else ''} "
                f"gross ${row.gross_sales:,.2f}",
    )
    db.commit()
    return _summary_response(db, sid, d)


@router.delete("/closes/{close_id}", response_model=DayCloseSummaryResponse)
def delete_close_route(
    close_id: int = Path(..., ge=1),
    db: Session = Depends(get_db),
    claims: dict[str, Any] = Depends(get_principal),
) -> DayCloseSummaryResponse:
    sid = resolve_store_scope(claims)
    require_permission(claims, "day_close", "update")
    try:
        row = delete_register_close(db, sid, close_id)
    except DayCloseNotFoundError:
        raise HTTPException(
            status_code=404, detail="Register close not found",
        )
    d = row.report_date
    _audit(
        db, claims=claims, action="delete_register_close",
        target_type="register_close", target_id=str(close_id),
        summary=f"{d.isoformat()} {row.register_label}"
                f"{' / ' + row.shift_label if row.shift_label else ''}",
    )
    db.commit()
    return _summary_response(db, sid, d)
