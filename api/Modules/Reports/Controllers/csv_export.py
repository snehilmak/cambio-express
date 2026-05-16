"""CSV export endpoints for the Reports module.

Registry-driven so adding a new report is a single-line entry.
Each row pairs a Service function with the columns + row formatter
needed to emit a CSV. Routes are registered on the same
`router` exported from `api.Modules.Reports.Controllers`, so they
mount at `/api/v2/reports/<slug>.csv`.

Auth + scope:
  * Caller authenticates via Bearer JWT (`Depends(get_principal)`).
  * `store_ids` is taken from the query string (same as the JSON
    drilldown). We verify the caller has access to every requested
    store — admins + employees are pinned to their own store;
    owners get every store under their umbrella; superadmins can
    request any.
  * The Flask side used to read the role from the Flask cookie
    session, which was empty in production (the SPA auths via
    JWT, not cookie), so downloads silently returned empty CSVs.
    This route fixes that bug by relying on the JWT.

Superadmin / platform-scope reports live in
`api.Modules.Superadmin.Controllers` (separate router prefix); the
registry + emitter helper here is shared via `_emit_csv()`.
"""
from __future__ import annotations

import csv
import io
from datetime import date, datetime
from typing import Any, Callable

from fastapi import Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from api.Core.Database import get_db
from api.Modules.Auth.Controllers import get_principal
from api.Modules.Owners.Services import owner_store_ids
from api.Modules.Reports.Services import (
    ach_volume, bank_charges_by_account, bank_rule_audit,
    bank_txn_breakdown, by_destination_country, cancelled_transfers,
    cashier_productivity, check_deposits, daily_drops,
    employee_activity, fees_vs_tax, high_value_transfers,
    new_vs_returning, period_comparison, period_pl,
    returned_check_status, sales_by_company, sales_by_employee,
    sales_by_service, top_customers, top_recipients,
)
from api.Modules.Tenancy.Models import User


# ── Period parsing (mirrors the JSON drilldown's parse_period) ──


def _parse_period(args: dict[str, str | None]) -> tuple[date, date, str]:
    today = date.today()
    default_from = date(today.year, today.month, 1)
    raw_from = (args.get("from_") or "").strip()
    raw_to   = (args.get("to") or "").strip()
    try:
        d_from = datetime.strptime(raw_from, "%Y-%m-%d").date() if raw_from else default_from
    except ValueError:
        d_from = default_from
    try:
        d_to = datetime.strptime(raw_to, "%Y-%m-%d").date() if raw_to else today
    except ValueError:
        d_to = today
    if d_from > d_to:
        d_from, d_to = d_to, d_from
    label = f"{d_from.strftime('%b %d, %Y')} – {d_to.strftime('%b %d, %Y')}"
    return d_from, d_to, label


def _parse_compare_dates(args: dict[str, str | None]) -> dict[str, date | None]:
    def _parse(name: str) -> date | None:
        raw = (args.get(name) or "").strip()
        if not raw:
            return None
        try:
            return datetime.strptime(raw, "%Y-%m-%d").date()
        except ValueError:
            return None
    return {"compare_from": _parse("compare_from"),
            "compare_to":   _parse("compare_to")}


def _parse_threshold(args: dict[str, str | None], default: float = 3000.0) -> float:
    try:
        v = float(args.get("threshold") or default)
    except (ValueError, TypeError):
        v = default
    return max(0.0, v)


# ── Scope authorization ─────────────────────────────────────


def _authorize_store_scope(
    db: Session, claims: dict, requested_store_ids: list[int],
) -> list[int]:
    """Resolve the final list of store_ids the caller is allowed to query.

    * Superadmin: pass-through (no umbrella filter); empty list
      means "all stores" — the services interpret that as no
      filter, which matches the platform-scope behaviour.
    * Owner: intersect requested ids with `owner_store_ids(user)`.
      Empty intersection is a 403 to make accidental misuse loud.
    * Admin / employee: must match the user's own `store_id`.
    """
    role = claims.get("role")
    user_id = claims.get("sub")
    store_id = claims.get("store_id")

    if role == "superadmin":
        return list(requested_store_ids)
    if role == "owner":
        u = db.get(User, user_id) if user_id else None
        allowed = set(owner_store_ids(db, u)) if u else set()
        if not requested_store_ids:
            return list(allowed)
        scoped = [sid for sid in requested_store_ids if sid in allowed]
        if not scoped:
            raise HTTPException(
                status_code=403,
                detail="Requested store_ids fall outside your owner umbrella.",
            )
        return scoped
    if role in ("admin", "employee"):
        if store_id is None:
            raise HTTPException(status_code=403, detail="No store on token.")
        if not requested_store_ids:
            return [store_id]
        if any(sid != store_id for sid in requested_store_ids):
            raise HTTPException(
                status_code=403,
                detail="Cannot query store_ids outside your own store.",
            )
        return [store_id]
    raise HTTPException(status_code=403, detail="Unknown role.")


# ── CSV emit helpers ────────────────────────────────────────


def _csv_response(buf: io.StringIO, fname: str) -> Response:
    return Response(
        content=buf.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


def _emit_csv(
    *, rows: list, totals: Any,
    columns: list[str] | Callable[[Any], list[str]],
    row_fn: Callable[[Any], list],
    totals_fn: Callable[[Any], list] | None,
    fname_prefix: str, d_from: date, d_to: date,
) -> Response:
    buf = io.StringIO()
    w = csv.writer(buf)
    cols = columns(totals) if callable(columns) else columns
    w.writerow(cols)
    for r in rows:
        w.writerow(row_fn(r))
    if totals_fn is not None:
        result = totals_fn(totals)
        totals_rows = (
            result if result and isinstance(result[0], (list, tuple))
            else [result]
        )
        if totals_rows:
            w.writerow([])
            for trow in totals_rows:
                w.writerow(trow)
    fname = f"{fname_prefix}_{d_from.isoformat()}_{d_to.isoformat()}.csv"
    return _csv_response(buf, fname)


# ── Store-scope registry ────────────────────────────────────


def _spec(
    *, service, columns, row_fn, totals_fn=None, fname_prefix=None,
    extra_args_fn=None,
):
    """Single registry row. ``extra_args_fn`` receives the query-arg
    dict and returns extra kwargs to forward to the service."""
    return {
        "service": service, "columns": columns, "row_fn": row_fn,
        "totals_fn": totals_fn, "fname_prefix": fname_prefix,
        "extra_args_fn": extra_args_fn,
    }


_STORE_REGISTRY: dict[str, dict] = {
    "sales-by-company": _spec(
        service=sales_by_company,
        columns=['Company', 'Count', 'Total Sent', 'Total Fees', 'Federal Tax', 'Avg Transfer'],
        row_fn=lambda r: [r['company'], r['count'], f"{r['sent']:.2f}", f"{r['fees']:.2f}", f"{r['tax']:.2f}", f"{r['avg']:.2f}"],
        totals_fn=lambda t: ['TOTAL', t['count'], f"{t['sent']:.2f}", f"{t['fees']:.2f}", f"{t['tax']:.2f}", ''],
    ),
    "sales-by-service-type": _spec(
        service=sales_by_service,
        columns=['Service Type', 'Count', 'Total Sent', 'Total Fees', 'Federal Tax', 'Avg Transfer'],
        row_fn=lambda r: [r['service_type'], r['count'], f"{r['sent']:.2f}", f"{r['fees']:.2f}", f"{r['tax']:.2f}", f"{r['avg']:.2f}"],
        totals_fn=lambda t: ['TOTAL', t['count'], f"{t['sent']:.2f}", f"{t['fees']:.2f}", f"{t['tax']:.2f}", ''],
    ),
    "sales-by-employee": _spec(
        service=sales_by_employee,
        columns=['Employee', 'Username', 'Count', 'Total Sent', 'Total Fees', 'Federal Tax', 'Avg Transfer'],
        row_fn=lambda r: [r['employee'], r['username'], r['count'], f"{r['sent']:.2f}", f"{r['fees']:.2f}", f"{r['tax']:.2f}", f"{r['avg']:.2f}"],
        totals_fn=lambda t: ['TOTAL', '', t['count'], f"{t['sent']:.2f}", f"{t['fees']:.2f}", f"{t['tax']:.2f}", ''],
    ),
    "cashier-productivity": _spec(
        service=cashier_productivity,
        columns=['Cashier', 'Active', 'Count', 'Total Sent', 'Total Fees', 'Federal Tax', 'Avg Transfer'],
        row_fn=lambda r: [r['cashier'], 'yes' if r['is_active'] else 'no', r['count'], f"{r['sent']:.2f}", f"{r['fees']:.2f}", f"{r['tax']:.2f}", f"{r['avg']:.2f}"],
        totals_fn=lambda t: ['TOTAL', '', t['count'], f"{t['sent']:.2f}", f"{t['fees']:.2f}", f"{t['tax']:.2f}", ''],
    ),
    "top-customers": _spec(
        service=top_customers,
        columns=['Customer', 'Phone', 'Count', 'Total Sent', 'Total Fees', 'Federal Tax', 'Avg Transfer'],
        row_fn=lambda r: [r['customer'], r['phone'], r['count'], f"{r['sent']:.2f}", f"{r['fees']:.2f}", f"{r['tax']:.2f}", f"{r['avg']:.2f}"],
    ),
    "top-senders": _spec(
        service=lambda db, store_ids, d_from, d_to, **_: top_customers(db, store_ids, d_from, d_to, sort_by='count'),
        columns=['Customer', 'Phone', 'Count', 'Total Sent', 'Total Fees', 'Federal Tax', 'Avg Transfer'],
        row_fn=lambda r: [r['customer'], r['phone'], r['count'], f"{r['sent']:.2f}", f"{r['fees']:.2f}", f"{r['tax']:.2f}", f"{r['avg']:.2f}"],
    ),
    "top-recipients": _spec(
        service=top_recipients,
        columns=['Recipient', 'Count', 'Total Sent', 'Total Fees', 'Federal Tax', 'Avg Transfer'],
        row_fn=lambda r: [r['recipient'], r['count'], f"{r['sent']:.2f}", f"{r['fees']:.2f}", f"{r['tax']:.2f}", f"{r['avg']:.2f}"],
    ),
    "by-destination-country": _spec(
        service=by_destination_country,
        columns=['Country', 'Count', 'Total Sent', 'Total Fees', 'Federal Tax', 'Avg Transfer'],
        row_fn=lambda r: [r['country'], r['count'], f"{r['sent']:.2f}", f"{r['fees']:.2f}", f"{r['tax']:.2f}", f"{r['avg']:.2f}"],
        totals_fn=lambda t: ['TOTAL', t['count'], f"{t['sent']:.2f}", f"{t['fees']:.2f}", f"{t['tax']:.2f}", ''],
    ),
    "new-vs-returning": _spec(
        service=new_vs_returning,
        columns=['Bucket', 'Customers', 'Transfers', 'Total Sent'],
        row_fn=lambda r: [r['bucket'], r['customers'], r['txns'], f"{r['sent']:.2f}"],
        totals_fn=lambda t: ['TOTAL', t['customers'], t['txns'], f"{t['sent']:.2f}"],
    ),
    "returned-check-status": _spec(
        service=returned_check_status,
        columns=['Status', 'Count', 'Amount', 'Recovered'],
        row_fn=lambda r: [r['status'], r['count'], f"{r['amount']:.2f}", f"{r['recovered']:.2f}"],
        totals_fn=lambda t: [['TOTAL', t['count'], f"{t['amount']:.2f}", f"{t['recovered']:.2f}"], ['NET G/L', '', '', f"{t['net_gl']:.2f}"]],
        fname_prefix='returned-checks',
    ),
    "bank-transactions-breakdown": _spec(
        service=bank_txn_breakdown,
        columns=['Category', 'Count', 'Signed Amount', 'Absolute Amount'],
        row_fn=lambda r: [r['label'], r['count'], f"{r['signed']:.2f}", f"{r['amount']:.2f}"],
        fname_prefix='bank-txn-breakdown',
    ),
    "daily-drops": _spec(
        service=daily_drops,
        columns=['Date', 'Drop Count', 'Total Dropped'],
        row_fn=lambda r: [r['date'].isoformat(), r['count'], f"{r['amount']:.2f}"],
        totals_fn=lambda t: ['TOTAL', t['count'], f"{t['amount']:.2f}"],
    ),
    "check-deposits": _spec(
        service=check_deposits,
        columns=['Date', 'Deposit Count', 'Total Deposited'],
        row_fn=lambda r: [r['date'].isoformat(), r['count'], f"{r['amount']:.2f}"],
        totals_fn=lambda t: ['TOTAL', t['count'], f"{t['amount']:.2f}"],
    ),
    "high-value-transfers": _spec(
        service=high_value_transfers,
        columns=['Date', 'Sender', 'Recipient', 'Country', 'Company', 'Send Amount', 'Fee', 'Federal Tax', 'Confirm #'],
        row_fn=lambda r: [r['send_date'].isoformat(), r['sender_name'], r['recipient_name'], r['country'], r['company'], f"{r['amount']:.2f}", f"{r['fee']:.2f}", f"{r['tax']:.2f}", r['confirm']],
        extra_args_fn=lambda args: {'threshold': _parse_threshold(args)},
    ),
    "employee-activity": _spec(
        service=employee_activity,
        columns=['Employee', 'Username', 'Active Transfers', 'Total Sent', 'Cancelled / Rejected', 'Last Activity'],
        row_fn=lambda r: [r['employee'], r['username'], r['count'], f"{r['sent']:.2f}", r['cancels'], r['last_activity'].isoformat() if r['last_activity'] else ''],
    ),
    "bank-rule-audit": _spec(
        service=bank_rule_audit,
        columns=['Rule', 'Match', 'Target', 'Matched Count', 'Total Amount'],
        row_fn=lambda r: [r['label'], r['match'], r['target'], r['count'], f"{r['amount']:.2f}"],
    ),
    "cancelled-transfers": _spec(
        service=cancelled_transfers,
        columns=['Date', 'Sender', 'Recipient', 'Country', 'Company', 'Status', 'Send Amount', 'Notes', 'Confirm #'],
        row_fn=lambda r: [r['send_date'].isoformat(), r['sender_name'], r['recipient_name'], r['country'], r['company'], r['status'], f"{r['amount']:.2f}", r['status_notes'], r['confirm']],
    ),
    "period-pl": _spec(
        service=period_pl,
        columns=['Section', 'Line', 'Amount'],
        row_fn=lambda r: [r['section'], r['label'], f"{r['amount']:.2f}"],
        totals_fn=lambda t: [['', 'Total Income', f"{t['income']:.2f}"], ['', 'Total Expenses', f"{t['expenses']:.2f}"], ['', 'Net', f"{t['net']:.2f}"]],
    ),
    "ach-volume": _spec(
        service=ach_volume,
        columns=['Company', 'Batch Count', 'Total ACH', 'Avg / Batch'],
        row_fn=lambda r: [r['company'], r['count'], f"{r['amount']:.2f}", f"{r['avg']:.2f}"],
        totals_fn=lambda t: ['TOTAL', t['count'], f"{t['amount']:.2f}", ''],
    ),
    "bank-charges-by-account": _spec(
        service=bank_charges_by_account,
        columns=['Account', 'Last 4', 'Charge Count', 'Total Charges', 'Avg / Charge'],
        row_fn=lambda r: [r['account'], r['last4'], r['count'], f"{r['amount']:.2f}", f"{r['avg']:.2f}"],
    ),
    "period-comparison": _spec(
        service=period_comparison,
        columns=lambda t: ['Metric', t['current_label'], t['prior_label'], 'Delta', '% Change'],
        row_fn=lambda r: [r['label'], f"{r['current']:.2f}" if r['is_money'] else f"{int(r['current'])}", f"{r['prior']:.2f}" if r['is_money'] else f"{int(r['prior'])}", f"{r['delta']:.2f}" if r['is_money'] else f"{int(r['delta'])}", f"{r['pct']:+.1f}%"],
        extra_args_fn=lambda args: _parse_compare_dates(args),
    ),
    "fees-vs-tax": _spec(
        service=fees_vs_tax,
        columns=['Line', 'Amount'],
        row_fn=lambda r: [r['label'], f"{r['amount']:.2f}"],
        totals_fn=lambda t: ['Tax / Fee Ratio', f"{t['ratio']:.2f}"],
    ),
}


# ── Public dispatcher ───────────────────────────────────────


def store_csv_export(
    slug: str,
    *,
    from_: str | None,
    to: str | None,
    store_ids_raw: str,
    threshold: str | None,
    compare_from: str | None,
    compare_to: str | None,
    db: Session,
    claims: dict,
) -> Response:
    """Dispatcher used by the FastAPI route. Splits out so tests
    can reach it without spinning up the full ASGI stack."""
    spec = _STORE_REGISTRY.get(slug)
    if spec is None:
        raise HTTPException(status_code=404, detail=f"Unknown report '{slug}'.")
    try:
        requested = [int(s.strip()) for s in (store_ids_raw or "").split(",") if s.strip()]
    except ValueError:
        raise HTTPException(status_code=422, detail="store_ids must be comma-separated integers.")
    if not requested:
        raise HTTPException(status_code=422, detail="store_ids must include at least one ID.")
    store_ids = _authorize_store_scope(db, claims, requested)

    args = {
        "from_": from_, "to": to,
        "threshold": threshold,
        "compare_from": compare_from, "compare_to": compare_to,
    }
    d_from, d_to, _ = _parse_period(args)
    extra_kwargs = spec["extra_args_fn"](args) if spec["extra_args_fn"] else {}
    rows, totals = spec["service"](db, store_ids, d_from, d_to, **extra_kwargs)
    return _emit_csv(
        rows=rows, totals=totals,
        columns=spec["columns"], row_fn=spec["row_fn"],
        totals_fn=spec["totals_fn"],
        fname_prefix=spec["fname_prefix"] or slug,
        d_from=d_from, d_to=d_to,
    )


def register(router) -> None:
    """Attach the store-scope CSV route onto the Reports router."""

    @router.get("/{slug}.csv")
    def csv_export(
        slug: str,
        from_: str | None = Query(None, alias="from"),
        to: str | None = Query(None),
        store_ids: str = Query(""),
        threshold: str | None = Query(None),
        compare_from: str | None = Query(None),
        compare_to: str | None = Query(None),
        db: Session = Depends(get_db),
        claims: dict = Depends(get_principal),
    ) -> Response:
        return store_csv_export(
            slug,
            from_=from_, to=to,
            store_ids_raw=store_ids,
            threshold=threshold,
            compare_from=compare_from, compare_to=compare_to,
            db=db, claims=claims,
        )


# ── Superadmin / platform-scope registry ────────────────────


from api.Modules.Superadmin.Services import (  # noqa: E402
    active_stores_by_plan, bank_sync_adoption, churn_cohort,
    conversion_rate, dau_mau, failed_payments, login_activity,
    mrr_arr, owner_adoption, passkey_adoption, password_resets,
    payouts, refunds, retention_queue, signup_funnel,
    suspended_stores, time_to_convert, trial_expiry_timing,
    tv_display_adoption, webhook_health,
)


def _sa_spec(*, service, columns, row_fn, totals_fn=None, fname_prefix=None):
    return {
        "service": service, "columns": columns, "row_fn": row_fn,
        "totals_fn": totals_fn, "fname_prefix": fname_prefix,
    }


_SA_REGISTRY: dict[str, dict] = {
    "active-stores-by-plan": _sa_spec(
        service=active_stores_by_plan,
        columns=['Plan', 'Stores'],
        row_fn=lambda r: [r['plan'], r['count']],
        totals_fn=lambda t: ['TOTAL', t['count']],
        fname_prefix='active-stores-by-plan',
    ),
    "signup-funnel": _sa_spec(
        service=signup_funnel,
        columns=['Plan', 'Signups'],
        row_fn=lambda r: [r['plan'], r['count']],
        totals_fn=lambda t: ['TOTAL', t['count']],
    ),
    "login-activity": _sa_spec(
        service=login_activity,
        columns=['Role', 'Active Users'],
        row_fn=lambda r: [r['role'], r['count']],
        totals_fn=lambda t: ['TOTAL', t['count']],
    ),
    "mrr-arr": _sa_spec(
        service=mrr_arr,
        columns=['Plan', 'Cycle', 'Stores', 'MRR', 'ARR'],
        row_fn=lambda r: [r['plan'], r['cycle'], r['stores'], f"{r['mrr']:.2f}", f"{r['arr']:.2f}"],
        totals_fn=lambda t: ['TOTAL', '', t['stores'], f"{t['mrr']:.2f}", f"{t['arr']:.2f}"],
    ),
    "churn-cohort": _sa_spec(
        service=churn_cohort,
        columns=['Cohort', 'Cancelled', 'Still Active', 'Churn %'],
        row_fn=lambda r: [r['cohort'], r['cancelled'], r['active'], f"{r['churn_pct']:.1f}%"],
    ),
    "conversion-rate": _sa_spec(
        service=conversion_rate,
        columns=['Status', 'Stores'],
        row_fn=lambda r: [r['label'], r['count']],
        totals_fn=lambda t: ['TOTAL', t['total']],
    ),
    "time-to-convert": _sa_spec(
        service=time_to_convert,
        columns=['Slug', 'Name', 'Plan', 'Signed Up', 'Days Active'],
        row_fn=lambda r: [r['slug'], r['name'], r['plan'], r['signed_up'].isoformat(), r['days']],
    ),
    "trial-expiry-timing": _sa_spec(
        service=trial_expiry_timing,
        columns=['Bucket', 'Stores'],
        row_fn=lambda r: [r['bucket'], r['count']],
    ),
    "bank-sync-adoption": _sa_spec(
        service=bank_sync_adoption,
        columns=['Plan', 'Connected', 'Total', 'Adoption %'],
        row_fn=lambda r: [r['plan'], r['connected'], r['total'], f"{r['rate_pct']:.1f}%"],
    ),
    "tv-display-adoption": _sa_spec(
        service=tv_display_adoption,
        columns=['Slug', 'Name', 'Plan'],
        row_fn=lambda r: [r['slug'], r['name'], r['plan']],
    ),
    "owner-adoption": _sa_spec(
        service=owner_adoption,
        columns=['Owner', 'Email', 'Linked Stores'],
        row_fn=lambda r: [r['owner'], r['email'], r['stores']],
    ),
    "passkey-adoption": _sa_spec(
        service=passkey_adoption,
        columns=['Role', 'Users with Passkey'],
        row_fn=lambda r: [r['role'], r['count']],
    ),
    "password-resets": _sa_spec(
        service=password_resets,
        columns=['Created', 'Username', 'Role', 'Status'],
        row_fn=lambda r: [r['created_at'].isoformat() if r['created_at'] else '', r['username'], r['role'], r['status']],
    ),
    "suspended-stores": _sa_spec(
        service=suspended_stores,
        columns=['Slug', 'Name', 'Plan', 'Reason'],
        row_fn=lambda r: [r['slug'], r['name'], r['plan'], r['reason']],
    ),
    "retention-queue": _sa_spec(
        service=retention_queue,
        columns=['Slug', 'Name', 'Plan', 'Purge Date', 'Days Left'],
        row_fn=lambda r: [r['slug'], r['name'], r['plan'], r['until'].isoformat() if r['until'] else '', r['days_left']],
    ),
    "refunds": _sa_spec(
        service=refunds,
        columns=['Reason', 'Count', 'Amount'],
        row_fn=lambda r: [r['reason'], r['count'], f"{r['amount']:.2f}"],
        totals_fn=lambda t: ['TOTAL', t['count'], f"{t['amount']:.2f}"],
    ),
    "failed-payments": _sa_spec(
        service=failed_payments,
        columns=['Reason', 'Count', 'Amount'],
        row_fn=lambda r: [r['reason'], r['count'], f"{r['amount']:.2f}"],
        totals_fn=lambda t: ['TOTAL', t['count'], f"{t['amount']:.2f}"],
    ),
    "payouts": _sa_spec(
        service=payouts,
        columns=['Payout ID', 'Amount', 'Status', 'Method', 'Arrival'],
        row_fn=lambda r: [r['id'], f"{r['amount']:.2f}", r['status'], r['method'], r['arrival'].isoformat() if r['arrival'] else ''],
        totals_fn=lambda t: ['TOTAL', f"{t['amount']:.2f}", '', '', ''],
    ),
    "dau-mau": _sa_spec(
        service=dau_mau,
        columns=['Date', 'Active Users'],
        row_fn=lambda r: [str(r['day']), r['users']],
        totals_fn=lambda t: ['TOTAL (MAU)', t['mau']],
    ),
    "webhook-health": _sa_spec(
        service=webhook_health,
        columns=['Status', 'Count'],
        row_fn=lambda r: [r['status'], r['count']],
        totals_fn=lambda t: ['TOTAL', t['count']],
    ),
}


def superadmin_csv_export(
    slug: str, *, from_: str | None, to: str | None,
    db: Session, claims: dict,
) -> Response:
    """Dispatcher for /api/v2/superadmin/reports/<slug>.csv."""
    if claims.get("role") != "superadmin":
        raise HTTPException(status_code=403, detail="Superadmin only.")
    spec = _SA_REGISTRY.get(slug)
    if spec is None:
        raise HTTPException(status_code=404, detail=f"Unknown report '{slug}'.")
    args = {"from_": from_, "to": to}
    d_from, d_to, _ = _parse_period(args)
    result = spec["service"](db, d_from, d_to)
    # Services return either (rows, totals) or (rows, totals, extras).
    rows = result[0]
    totals = result[1] if len(result) > 1 else {}
    return _emit_csv(
        rows=rows, totals=totals,
        columns=spec["columns"], row_fn=spec["row_fn"],
        totals_fn=spec["totals_fn"],
        fname_prefix=spec["fname_prefix"] or slug,
        d_from=d_from, d_to=d_to,
    )


def register_superadmin(router) -> None:
    """Attach the platform-scope CSV route onto the Superadmin router."""

    @router.get("/reports/{slug}.csv")
    def csv_export(
        slug: str,
        from_: str | None = Query(None, alias="from"),
        to: str | None = Query(None),
        db: Session = Depends(get_db),
        claims: dict = Depends(get_principal),
    ) -> Response:
        return superadmin_csv_export(
            slug, from_=from_, to=to, db=db, claims=claims,
        )
