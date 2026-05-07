"""Reports module — Controllers (FastAPI router).

The router mounts at `/api/v2/reports/*` (the parent router in
`api/main.py` carries the `/api/v2` prefix; this one adds
`/reports`).

Each route is a thin shell:
  1. FastAPI parses query params via `Depends(parse_period)` and
     `Depends(parse_store_ids)`.
  2. The route calls a Service function with `(db, store_ids,
     d_from, d_to[, ...])`.
  3. The service's `(rows, totals)` tuple is wrapped in the
     matching `*Response` Pydantic schema and returned.

No auth on these routes today — auth migration is module 5 of 6
in the migration order. The dispatch path is internal-only at this
point (Flask still serves the user-facing `/reports/*` HTML pages),
so missing auth doesn't expose anything to end users yet. PR
that adds auth will gate every route here behind a JWT dependency.

Layer rules from the ADR:
    Controller → Service     ✓
    Controller → Repository  ✗
    Controller → DB session  ✓ (only via `Depends(get_db)`)
    Controller → Provider    ✗
"""
from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from api.Core.Database import get_db
from api.Modules.Reports.Requests import (
    ByDestinationCountryResponse,
    CashierProductivityResponse,
    SalesByCompanyResponse,
    SalesByEmployeeResponse,
    SalesByServiceResponse,
    TopCustomersResponse,
    TopRecipientsResponse,
)
from api.Modules.Reports.Services import (
    by_destination_country,
    cashier_productivity,
    sales_by_company,
    sales_by_employee,
    sales_by_service,
    top_customers,
    top_recipients,
)


router = APIRouter()


# ── Shared dependencies ─────────────────────────────────────


def parse_period(
    from_: str | None = Query(
        None,
        alias="from",
        description=(
            "Start date in YYYY-MM-DD. Defaults to the first of the "
            "current month."
        ),
    ),
    to: str | None = Query(
        None,
        description="End date in YYYY-MM-DD. Defaults to today.",
    ),
) -> tuple[date, date]:
    """Mirrors `app.py::_report_period`. Two YYYY-MM-DD strings,
    parsed with sane defaults; if `from > to`, swap them so callers
    can't construct an empty range by mistake.

    Returned as a tuple so endpoints can `d_from, d_to = period`.
    """
    today = date.today()
    default_from = date(today.year, today.month, 1)
    try:
        d_from = datetime.strptime(from_, "%Y-%m-%d").date() if from_ else default_from
    except ValueError:
        d_from = default_from
    try:
        d_to = datetime.strptime(to, "%Y-%m-%d").date() if to else today
    except ValueError:
        d_to = today
    if d_from > d_to:
        d_from, d_to = d_to, d_from
    return d_from, d_to


def parse_store_ids(
    store_ids: str = Query(
        ...,
        description=(
            "Comma-separated store IDs, e.g. `1,2`. Single-tenant "
            "deployments will pass just one. Multi-store owners pass "
            "every store under their umbrella."
        ),
    ),
) -> list[int]:
    """Parse `?store_ids=1,2,3` into `[1, 2, 3]`. Rejects empty
    strings and non-numeric values via FastAPI's 422 validation
    when the cast fails."""
    try:
        ids = [int(s.strip()) for s in store_ids.split(",") if s.strip()]
    except ValueError as e:
        raise HTTPException(
            status_code=422,
            detail=f"store_ids must be comma-separated integers: {e}",
        )
    if not ids:
        raise HTTPException(
            status_code=422, detail="store_ids must include at least one ID",
        )
    return ids


# ── Routes ──────────────────────────────────────────────────


@router.get("/sales-by-company", response_model=SalesByCompanyResponse)
def sales_by_company_route(
    period: tuple[date, date] = Depends(parse_period),
    store_ids: list[int] = Depends(parse_store_ids),
    db: Session = Depends(get_db),
) -> SalesByCompanyResponse:
    d_from, d_to = period
    rows, totals = sales_by_company(db, store_ids, d_from, d_to)
    return SalesByCompanyResponse(rows=rows, totals=totals)


@router.get("/sales-by-service", response_model=SalesByServiceResponse)
def sales_by_service_route(
    period: tuple[date, date] = Depends(parse_period),
    store_ids: list[int] = Depends(parse_store_ids),
    db: Session = Depends(get_db),
) -> SalesByServiceResponse:
    d_from, d_to = period
    rows, totals = sales_by_service(db, store_ids, d_from, d_to)
    return SalesByServiceResponse(rows=rows, totals=totals)


@router.get(
    "/by-destination-country",
    response_model=ByDestinationCountryResponse,
)
def by_destination_country_route(
    period: tuple[date, date] = Depends(parse_period),
    store_ids: list[int] = Depends(parse_store_ids),
    db: Session = Depends(get_db),
) -> ByDestinationCountryResponse:
    d_from, d_to = period
    rows, totals = by_destination_country(db, store_ids, d_from, d_to)
    return ByDestinationCountryResponse(rows=rows, totals=totals)


@router.get("/top-recipients", response_model=TopRecipientsResponse)
def top_recipients_route(
    period: tuple[date, date] = Depends(parse_period),
    store_ids: list[int] = Depends(parse_store_ids),
    limit: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db),
) -> TopRecipientsResponse:
    d_from, d_to = period
    rows, totals = top_recipients(db, store_ids, d_from, d_to, limit=limit)
    return TopRecipientsResponse(rows=rows, totals=totals)


@router.get("/top-customers", response_model=TopCustomersResponse)
def top_customers_route(
    period: tuple[date, date] = Depends(parse_period),
    store_ids: list[int] = Depends(parse_store_ids),
    sort_by: str = Query(
        "sent",
        pattern="^(sent|count)$",
        description=(
            "Either `sent` (top spenders) or `count` (most-active senders)."
        ),
    ),
    limit: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db),
) -> TopCustomersResponse:
    d_from, d_to = period
    rows, totals = top_customers(
        db, store_ids, d_from, d_to, sort_by=sort_by, limit=limit,
    )
    return TopCustomersResponse(rows=rows, totals=totals)


@router.get("/sales-by-employee", response_model=SalesByEmployeeResponse)
def sales_by_employee_route(
    period: tuple[date, date] = Depends(parse_period),
    store_ids: list[int] = Depends(parse_store_ids),
    db: Session = Depends(get_db),
) -> SalesByEmployeeResponse:
    d_from, d_to = period
    rows, totals = sales_by_employee(db, store_ids, d_from, d_to)
    return SalesByEmployeeResponse(rows=rows, totals=totals)


@router.get(
    "/cashier-productivity",
    response_model=CashierProductivityResponse,
)
def cashier_productivity_route(
    period: tuple[date, date] = Depends(parse_period),
    store_ids: list[int] = Depends(parse_store_ids),
    db: Session = Depends(get_db),
) -> CashierProductivityResponse:
    d_from, d_to = period
    rows, totals = cashier_productivity(db, store_ids, d_from, d_to)
    return CashierProductivityResponse(rows=rows, totals=totals)
