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
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from api.Core.Database import get_db
from api.Modules.Auth.Controllers import get_principal
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


# ── Batch-3 drilldowns ──────────────────────────────────────
#
# These five reports return `{rows, totals}` from their existing
# Service functions. Pydantic schemas would add boilerplate without
# value — the SPA already accepts a generic `{rows, totals}` envelope
# (see `ReportDrilldownResponse` in frontend/src/api/reportDrilldown.ts).
# `response_model=None` skips schema generation but the JSON shape is
# stable: the SPA treats each row's identity field as a known string.


@router.get("/new-vs-returning")
def new_vs_returning_route(
    period: tuple[date, date] = Depends(parse_period),
    store_ids: list[int] = Depends(parse_store_ids),
    db: Session = Depends(get_db),
):
    from api.Modules.Reports.Services import new_vs_returning
    d_from, d_to = period
    rows, totals = new_vs_returning(db, store_ids, d_from, d_to)
    return {"rows": rows, "totals": totals}


@router.get("/fees-vs-tax")
def fees_vs_tax_route(
    period: tuple[date, date] = Depends(parse_period),
    store_ids: list[int] = Depends(parse_store_ids),
    db: Session = Depends(get_db),
):
    from api.Modules.Reports.Services import fees_vs_tax
    d_from, d_to = period
    rows, totals = fees_vs_tax(db, store_ids, d_from, d_to)
    return {"rows": rows, "totals": totals}


@router.get("/high-value-transfers")
def high_value_transfers_route(
    period: tuple[date, date] = Depends(parse_period),
    store_ids: list[int] = Depends(parse_store_ids),
    threshold: float = Query(1000.0, ge=0),
    db: Session = Depends(get_db),
):
    from api.Modules.Reports.Services import high_value_transfers
    d_from, d_to = period
    rows, totals = high_value_transfers(
        db, store_ids, d_from, d_to, threshold=threshold,
    )
    return {"rows": rows, "totals": totals, "threshold": threshold}


@router.get("/cancelled-transfers")
def cancelled_transfers_route(
    period: tuple[date, date] = Depends(parse_period),
    store_ids: list[int] = Depends(parse_store_ids),
    db: Session = Depends(get_db),
):
    from api.Modules.Reports.Services import cancelled_transfers
    d_from, d_to = period
    rows, totals = cancelled_transfers(db, store_ids, d_from, d_to)
    return {"rows": rows, "totals": totals}


@router.get("/ach-volume")
def ach_volume_route(
    period: tuple[date, date] = Depends(parse_period),
    store_ids: list[int] = Depends(parse_store_ids),
    db: Session = Depends(get_db),
):
    from api.Modules.Reports.Services import ach_volume
    d_from, d_to = period
    rows, totals = ach_volume(db, store_ids, d_from, d_to)
    return {"rows": rows, "totals": totals}


# ── Batch-4 drilldowns (audit + banking) ───────────────────


@router.get("/returned-check-status")
def returned_check_status_route(
    period: tuple[date, date] = Depends(parse_period),
    store_ids: list[int] = Depends(parse_store_ids),
    db: Session = Depends(get_db),
):
    from api.Modules.Reports.Services import returned_check_status
    d_from, d_to = period
    rows, totals = returned_check_status(db, store_ids, d_from, d_to)
    return {"rows": rows, "totals": totals}


@router.get("/bank-transactions-breakdown")
def bank_txn_breakdown_route(
    period: tuple[date, date] = Depends(parse_period),
    store_ids: list[int] = Depends(parse_store_ids),
    db: Session = Depends(get_db),
):
    from api.Modules.Reports.Services import bank_txn_breakdown
    d_from, d_to = period
    rows, totals = bank_txn_breakdown(db, store_ids, d_from, d_to)
    return {"rows": rows, "totals": totals}


@router.get("/daily-drops")
def daily_drops_route(
    period: tuple[date, date] = Depends(parse_period),
    store_ids: list[int] = Depends(parse_store_ids),
    db: Session = Depends(get_db),
):
    from api.Modules.Reports.Services import daily_drops
    d_from, d_to = period
    rows, totals = daily_drops(db, store_ids, d_from, d_to)
    return {"rows": rows, "totals": totals}


@router.get("/check-deposits")
def check_deposits_route(
    period: tuple[date, date] = Depends(parse_period),
    store_ids: list[int] = Depends(parse_store_ids),
    db: Session = Depends(get_db),
):
    from api.Modules.Reports.Services import check_deposits
    d_from, d_to = period
    rows, totals = check_deposits(db, store_ids, d_from, d_to)
    return {"rows": rows, "totals": totals}


@router.get("/bank-rule-audit")
def bank_rule_audit_route(
    period: tuple[date, date] = Depends(parse_period),
    store_ids: list[int] = Depends(parse_store_ids),
    db: Session = Depends(get_db),
):
    from api.Modules.Reports.Services import bank_rule_audit
    d_from, d_to = period
    rows, totals = bank_rule_audit(db, store_ids, d_from, d_to)
    return {"rows": rows, "totals": totals}


@router.get("/bank-charges-by-account")
def bank_charges_by_account_route(
    period: tuple[date, date] = Depends(parse_period),
    store_ids: list[int] = Depends(parse_store_ids),
    db: Session = Depends(get_db),
):
    from api.Modules.Reports.Services import bank_charges_by_account
    d_from, d_to = period
    rows, totals = bank_charges_by_account(db, store_ids, d_from, d_to)
    return {"rows": rows, "totals": totals}


@router.get("/period-comparison")
def period_comparison_route(
    period: tuple[date, date] = Depends(parse_period),
    store_ids: list[int] = Depends(parse_store_ids),
    compare_from: str | None = Query(None),
    compare_to: str | None = Query(None),
    db: Session = Depends(get_db),
):
    from datetime import datetime
    from api.Modules.Reports.Services import period_comparison
    d_from, d_to = period
    cf = (
        datetime.strptime(compare_from, "%Y-%m-%d").date()
        if compare_from else None
    )
    ct = (
        datetime.strptime(compare_to, "%Y-%m-%d").date()
        if compare_to else None
    )
    rows, totals = period_comparison(
        db, store_ids, d_from, d_to,
        compare_from=cf, compare_to=ct,
    )
    return {"rows": rows, "totals": totals}


@router.get("/employee-activity")
def employee_activity_route(
    period: tuple[date, date] = Depends(parse_period),
    store_ids: list[int] = Depends(parse_store_ids),
    db: Session = Depends(get_db),
):
    from api.Modules.Reports.Services import employee_activity
    d_from, d_to = period
    rows, totals = employee_activity(db, store_ids, d_from, d_to)
    return {"rows": rows, "totals": totals}


@router.get("/period-pl")
def period_pl_route(
    period: tuple[date, date] = Depends(parse_period),
    store_ids: list[int] = Depends(parse_store_ids),
    db: Session = Depends(get_db),
):
    from api.Modules.Reports.Services import period_pl
    d_from, d_to = period
    rows, totals = period_pl(db, store_ids, d_from, d_to)
    return {"rows": rows, "totals": totals}


# ── Report-center index ─────────────────────────────────────


class ReportRow(BaseModel):
    """One report card on the categorized index. `url` is the
    Flask drilldown path (legacy templates still own per-report
    rendering for now); `status` is `ready` or `coming_soon`."""
    model_config = ConfigDict(extra="forbid")

    key: str
    label: str
    description: str
    url: str | None
    status: str


class ReportCategory(BaseModel):
    """Group of related reports (Sales / Financial / Operations /
    Customers / Audit). The icon is an inline stroke SVG matching
    the rest of the design-system iconography (CLAUDE.md)."""
    model_config = ConfigDict(extra="forbid")

    key: str
    label: str
    icon: str
    reports: list[ReportRow]


class ReportListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    categories: list[ReportCategory]


def _build_report_list(prefix: str = "") -> ReportListResponse:
    """Resolve ``REPORT_CATEGORIES`` through the same resolver the
    legacy ``/reports`` + ``/owner/reports`` Flask routes used, then
    adapt to the SPA-shaped envelope. ``prefix`` mirrors the
    legacy ``endpoint_prefix='owner_'`` knob: empty for the admin
    index, ``'owner_'`` for the owner index."""
    from api.Modules.Reports.Services.categories import (
        REPORT_CATEGORIES, resolved_categories,
    )
    # Pure resolver — no Flask request context needed (the old
    # ``url_for`` lookup was a dead path after PR #503 deleted the
    # HTML drilldown routes; the convention-based fallback handled
    # every endpoint in practice).
    resolved = resolved_categories(REPORT_CATEGORIES, endpoint_prefix=prefix)
    return ReportListResponse(categories=[
        ReportCategory(
            key=cat["key"],
            label=cat["label"],
            icon=cat["icon"],
            reports=[
                ReportRow(
                    key=r["key"],
                    label=r["label"],
                    description=r["description"],
                    url=r.get("url"),
                    status=r["status"],
                )
                for r in cat["reports"]
            ],
        )
        for cat in resolved
    ])


@router.get("", response_model=ReportListResponse)
def list_reports_route(
    db: Session = Depends(get_db),  # noqa: ARG001 — kept for symmetry
    claims: dict = Depends(get_principal),
) -> ReportListResponse:
    """Per-store report-center categories for the admin Reports page.

    Mirrors the legacy /reports Jinja landing — same registry
    (`_REPORT_CATEGORIES`), same View / Coming-soon split, same
    drilldown URLs (still on Flask templates one PR-per-report
    until each report individually migrates).

    Auth: any logged-in caller scoped to a store. Owners get the
    same admin-side category list when viewing through their own
    store; the owner-prefix variant lives at /owner/reports."""
    if claims.get("role") not in ("admin", "owner", "employee", "superadmin"):
        raise HTTPException(
            status_code=403,
            detail="Sign in as a store user to view reports.",
        )
    return _build_report_list(prefix="")
