"""Legacy Flask CSV report routes — register on the Flask `app`.

These routes were declared inline in `app.py` and registered ~30
`/reports/<slug>.csv` / `/owner/reports/<slug>.csv` /
`/superadmin/reports/<slug>.csv` endpoints. The HTML drilldowns
already live on the SPA; only the CSV exports stay on Flask
because <a href> downloads can't attach an Authorization: Bearer.

Each `_make_report_routes(...)` call binds a Reports Service to a
CSV-export view function and registers admin + owner mirror URLs.
`_register_owner_report_mirrors()` (called at the end) shadow-
registers every admin route on `/owner/...` reusing the same
handler — scope flips inside the handler via `_report_scope_ids()`
reading session role.
"""
from __future__ import annotations

import csv
import io
from datetime import date, datetime

from flask import Response, request, session

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
from api.Modules.Superadmin.Services import (
    active_stores_by_plan, bank_sync_adoption, churn_cohort,
    conversion_rate, dau_mau, failed_payments, login_activity,
    mrr_arr, owner_adoption, passkey_adoption, password_resets,
    payouts, refunds, retention_queue, signup_funnel,
    suspended_stores, time_to_convert, trial_expiry_timing,
    tv_display_adoption, webhook_health,
)


def register(app, db, current_user_fn):
    """Wire every CSV report route onto the Flask `app`.

    Parameters
    ----------
    app : Flask
    db  : the app.py `db` shim (has `.session`)
    current_user_fn : callable returning the current User or None
    """

    def _report_period(args):
        """Parse ?from=YYYY-MM-DD&to=YYYY-MM-DD; default current month."""
        today = date.today()
        default_from = date(today.year, today.month, 1)
        raw_from = (args.get("from") or "").strip()
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

    def _report_scope_ids():
        """Admin → [own store_id]; owner → every linked store_id."""
        role = session.get("role")
        if role == "owner":
            u = current_user_fn()
            return owner_store_ids(db.session, u) if u else []
        sid = session.get("store_id")
        return [sid] if sid else []

    def _csv_response(buf, fname):
        return Response(buf.getvalue(), mimetype="text/csv",
            headers={"Content-Disposition": f'attachment; filename="{fname}"'})

    def _parse_threshold(args, default=3000):
        try:
            v = float(args.get("threshold") or default)
        except (ValueError, TypeError):
            v = default
        return max(0.0, v)

    def _parse_compare_dates(args):
        """Optional `compare_from` / `compare_to` for the Period
        Comparison report. Returns dict with both keys present
        (None if unparseable)."""
        def _parse(name):
            raw = (args.get(name) or "").strip()
            if not raw:
                return None
            try:
                return datetime.strptime(raw, "%Y-%m-%d").date()
            except ValueError:
                return None
        return {"compare_from": _parse("compare_from"),
                "compare_to":   _parse("compare_to")}

    def _service_fn(service):
        """Bind db.session to a (store_ids, d_from, d_to, **kw) Reports service."""
        def _inner(store_ids, d_from, d_to, **kwargs):
            return service(db.session, store_ids, d_from, d_to, **kwargs)
        return _inner

    def _sa_service_fn(service):
        """Bind db.session to a (d_from, d_to, **kw) Superadmin service."""
        def _inner(d_from, d_to, **kwargs):
            return service(db.session, d_from, d_to, **kwargs)
        return _inner

    def _run_report_csv(data_fn, *, scope, columns, row_fn,
                        totals_row_fn=None, fname_prefix,
                        extra_args=None):
        """Shared CSV emitter for store-scope + platform-scope reports."""
        extra_args = extra_args or {}
        d_from, d_to, _ = _report_period(request.args)
        if scope == "platform":
            rows, totals = data_fn(d_from, d_to, **extra_args)
        else:
            rows, totals = data_fn(_report_scope_ids(), d_from, d_to,
                                    **extra_args)
        buf = io.StringIO(); w = csv.writer(buf)
        cols = columns(totals) if callable(columns) else columns
        w.writerow(cols)
        for r in rows:
            w.writerow(row_fn(r))
        if totals_row_fn is not None:
            result = totals_row_fn(totals)
            totals_rows = (result if result and isinstance(result[0], (list, tuple))
                           else [result])
            if totals_rows:
                w.writerow([])
                for trow in totals_rows:
                    w.writerow(trow)
        return _csv_response(buf,
            f"{fname_prefix}_{d_from.isoformat()}_{d_to.isoformat()}.csv")

    def _make_report_routes(slug, *, data_fn, csv_columns, csv_row_fn,
                             csv_totals_fn=None, csv_fname_prefix=None,
                             extra_args_fn=None):
        """Register admin (/reports/<slug>.csv) CSV route. The owner
        mirror is shadow-registered by _register_owner_report_mirrors()."""
        fname_prefix = csv_fname_prefix or slug
        extra_args_fn = extra_args_fn or (lambda: {})
        underscored = slug.replace("-", "_")

        def _csv():
            return _run_report_csv(data_fn, scope="store",
                columns=csv_columns, row_fn=csv_row_fn,
                totals_row_fn=csv_totals_fn,
                fname_prefix=fname_prefix,
                extra_args=extra_args_fn(),
            )

        app.add_url_rule(f"/reports/{slug}.csv",
                         endpoint=f"report_{underscored}_csv",
                         view_func=_csv, methods=["GET"])
        app.add_url_rule(f"/owner/reports/{slug}.csv",
                         endpoint=f"owner_report_{underscored}_csv",
                         view_func=_csv, methods=["GET"])

    def _make_superadmin_report_routes(slug, *, data_fn, csv_columns,
                                        csv_row_fn, csv_totals_fn=None,
                                        csv_fname_prefix=None,
                                        extra_args_fn=None):
        """Register /superadmin/reports/<slug>.csv."""
        fname_prefix = csv_fname_prefix or slug
        extra_args_fn = extra_args_fn or (lambda: {})
        underscored = slug.replace("-", "_")

        def _csv():
            return _run_report_csv(data_fn, scope="platform",
                columns=csv_columns, row_fn=csv_row_fn,
                totals_row_fn=csv_totals_fn,
                fname_prefix=fname_prefix,
                extra_args=extra_args_fn(),
            )

        app.add_url_rule(f"/superadmin/reports/{slug}.csv",
                         endpoint=f"superadmin_report_{underscored}_csv",
                         view_func=_csv,
                         methods=["GET"])

    # ── Admin + owner reports ─────────────────────────────────
    _make_report_routes(
        'sales-by-company',
        data_fn=_service_fn(sales_by_company),
        csv_columns=['Company', 'Count', 'Total Sent', 'Total Fees', 'Federal Tax', 'Avg Transfer'],
        csv_row_fn=lambda r: [r['company'], r['count'], f"{r['sent']:.2f}", f"{r['fees']:.2f}", f"{r['tax']:.2f}", f"{r['avg']:.2f}"],
        csv_totals_fn=lambda t: ['TOTAL', t['count'], f"{t['sent']:.2f}", f"{t['fees']:.2f}", f"{t['tax']:.2f}", ''],
    )
    _make_report_routes(
        'sales-by-service-type',
        data_fn=_service_fn(sales_by_service),
        csv_columns=['Service Type', 'Count', 'Total Sent', 'Total Fees', 'Federal Tax', 'Avg Transfer'],
        csv_row_fn=lambda r: [r['service_type'], r['count'], f"{r['sent']:.2f}", f"{r['fees']:.2f}", f"{r['tax']:.2f}", f"{r['avg']:.2f}"],
        csv_totals_fn=lambda t: ['TOTAL', t['count'], f"{t['sent']:.2f}", f"{t['fees']:.2f}", f"{t['tax']:.2f}", ''],
    )
    _make_report_routes(
        'sales-by-employee',
        data_fn=_service_fn(sales_by_employee),
        csv_columns=['Employee', 'Username', 'Count', 'Total Sent', 'Total Fees', 'Federal Tax', 'Avg Transfer'],
        csv_row_fn=lambda r: [r['employee'], r['username'], r['count'], f"{r['sent']:.2f}", f"{r['fees']:.2f}", f"{r['tax']:.2f}", f"{r['avg']:.2f}"],
        csv_totals_fn=lambda t: ['TOTAL', '', t['count'], f"{t['sent']:.2f}", f"{t['fees']:.2f}", f"{t['tax']:.2f}", ''],
    )
    _make_report_routes(
        'cashier-productivity',
        data_fn=_service_fn(cashier_productivity),
        csv_columns=['Cashier', 'Active', 'Count', 'Total Sent', 'Total Fees', 'Federal Tax', 'Avg Transfer'],
        csv_row_fn=lambda r: [r['cashier'], 'yes' if r['is_active'] else 'no', r['count'], f"{r['sent']:.2f}", f"{r['fees']:.2f}", f"{r['tax']:.2f}", f"{r['avg']:.2f}"],
        csv_totals_fn=lambda t: ['TOTAL', '', t['count'], f"{t['sent']:.2f}", f"{t['fees']:.2f}", f"{t['tax']:.2f}", ''],
    )
    _make_report_routes(
        'top-customers',
        data_fn=_service_fn(top_customers),
        csv_columns=['Customer', 'Phone', 'Count', 'Total Sent', 'Total Fees', 'Federal Tax', 'Avg Transfer'],
        csv_row_fn=lambda r: [r['customer'], r['phone'], r['count'], f"{r['sent']:.2f}", f"{r['fees']:.2f}", f"{r['tax']:.2f}", f"{r['avg']:.2f}"],
    )
    _make_report_routes(
        'top-senders',
        data_fn=_service_fn(lambda db_session, store_ids, d_from, d_to, **_: top_customers(db_session, store_ids, d_from, d_to, sort_by='count')),
        csv_columns=['Customer', 'Phone', 'Count', 'Total Sent', 'Total Fees', 'Federal Tax', 'Avg Transfer'],
        csv_row_fn=lambda r: [r['customer'], r['phone'], r['count'], f"{r['sent']:.2f}", f"{r['fees']:.2f}", f"{r['tax']:.2f}", f"{r['avg']:.2f}"],
    )
    _make_report_routes(
        'top-recipients',
        data_fn=_service_fn(top_recipients),
        csv_columns=['Recipient', 'Count', 'Total Sent', 'Total Fees', 'Federal Tax', 'Avg Transfer'],
        csv_row_fn=lambda r: [r['recipient'], r['count'], f"{r['sent']:.2f}", f"{r['fees']:.2f}", f"{r['tax']:.2f}", f"{r['avg']:.2f}"],
    )
    _make_report_routes(
        'by-destination-country',
        data_fn=_service_fn(by_destination_country),
        csv_columns=['Country', 'Count', 'Total Sent', 'Total Fees', 'Federal Tax', 'Avg Transfer'],
        csv_row_fn=lambda r: [r['country'], r['count'], f"{r['sent']:.2f}", f"{r['fees']:.2f}", f"{r['tax']:.2f}", f"{r['avg']:.2f}"],
        csv_totals_fn=lambda t: ['TOTAL', t['count'], f"{t['sent']:.2f}", f"{t['fees']:.2f}", f"{t['tax']:.2f}", ''],
    )
    _make_report_routes(
        'new-vs-returning',
        data_fn=_service_fn(new_vs_returning),
        csv_columns=['Bucket', 'Customers', 'Transfers', 'Total Sent'],
        csv_row_fn=lambda r: [r['bucket'], r['customers'], r['txns'], f"{r['sent']:.2f}"],
        csv_totals_fn=lambda t: ['TOTAL', t['customers'], t['txns'], f"{t['sent']:.2f}"],
    )
    _make_report_routes(
        'returned-check-status',
        data_fn=_service_fn(returned_check_status),
        csv_columns=['Status', 'Count', 'Amount', 'Recovered'],
        csv_row_fn=lambda r: [r['status'], r['count'], f"{r['amount']:.2f}", f"{r['recovered']:.2f}"],
        csv_totals_fn=lambda t: [['TOTAL', t['count'], f"{t['amount']:.2f}", f"{t['recovered']:.2f}"], ['NET G/L', '', '', f"{t['net_gl']:.2f}"]],
        csv_fname_prefix='returned-checks',
    )
    _make_report_routes(
        'bank-transactions-breakdown',
        data_fn=_service_fn(bank_txn_breakdown),
        csv_columns=['Category', 'Count', 'Signed Amount', 'Absolute Amount'],
        csv_row_fn=lambda r: [r['label'], r['count'], f"{r['signed']:.2f}", f"{r['amount']:.2f}"],
        csv_fname_prefix='bank-txn-breakdown',
    )
    _make_report_routes(
        'daily-drops',
        data_fn=_service_fn(daily_drops),
        csv_columns=['Date', 'Drop Count', 'Total Dropped'],
        csv_row_fn=lambda r: [r['date'].isoformat(), r['count'], f"{r['amount']:.2f}"],
        csv_totals_fn=lambda t: ['TOTAL', t['count'], f"{t['amount']:.2f}"],
    )
    _make_report_routes(
        'check-deposits',
        data_fn=_service_fn(check_deposits),
        csv_columns=['Date', 'Deposit Count', 'Total Deposited'],
        csv_row_fn=lambda r: [r['date'].isoformat(), r['count'], f"{r['amount']:.2f}"],
        csv_totals_fn=lambda t: ['TOTAL', t['count'], f"{t['amount']:.2f}"],
    )
    _make_report_routes(
        'high-value-transfers',
        data_fn=_service_fn(high_value_transfers),
        csv_columns=['Date', 'Sender', 'Recipient', 'Country', 'Company', 'Send Amount', 'Fee', 'Federal Tax', 'Confirm #'],
        csv_row_fn=lambda r: [r['send_date'].isoformat(), r['sender_name'], r['recipient_name'], r['country'], r['company'], f"{r['amount']:.2f}", f"{r['fee']:.2f}", f"{r['tax']:.2f}", r['confirm']],
        extra_args_fn=lambda: {'threshold': _parse_threshold(request.args)},
    )
    _make_report_routes(
        'employee-activity',
        data_fn=_service_fn(employee_activity),
        csv_columns=['Employee', 'Username', 'Active Transfers', 'Total Sent', 'Cancelled / Rejected', 'Last Activity'],
        csv_row_fn=lambda r: [r['employee'], r['username'], r['count'], f"{r['sent']:.2f}", r['cancels'], r['last_activity'].isoformat() if r['last_activity'] else ''],
    )
    _make_report_routes(
        'bank-rule-audit',
        data_fn=_service_fn(bank_rule_audit),
        csv_columns=['Rule', 'Match', 'Target', 'Matched Count', 'Total Amount'],
        csv_row_fn=lambda r: [r['label'], r['match'], r['target'], r['count'], f"{r['amount']:.2f}"],
    )
    _make_report_routes(
        'cancelled-transfers',
        data_fn=_service_fn(cancelled_transfers),
        csv_columns=['Date', 'Sender', 'Recipient', 'Country', 'Company', 'Status', 'Send Amount', 'Notes', 'Confirm #'],
        csv_row_fn=lambda r: [r['send_date'].isoformat(), r['sender_name'], r['recipient_name'], r['country'], r['company'], r['status'], f"{r['amount']:.2f}", r['status_notes'], r['confirm']],
    )
    _make_report_routes(
        'period-pl',
        data_fn=_service_fn(period_pl),
        csv_columns=['Section', 'Line', 'Amount'],
        csv_row_fn=lambda r: [r['section'], r['label'], f"{r['amount']:.2f}"],
        csv_totals_fn=lambda t: [['', 'Total Income', f"{t['income']:.2f}"], ['', 'Total Expenses', f"{t['expenses']:.2f}"], ['', 'Net', f"{t['net']:.2f}"]],
    )
    _make_report_routes(
        'ach-volume',
        data_fn=_service_fn(ach_volume),
        csv_columns=['Company', 'Batch Count', 'Total ACH', 'Avg / Batch'],
        csv_row_fn=lambda r: [r['company'], r['count'], f"{r['amount']:.2f}", f"{r['avg']:.2f}"],
        csv_totals_fn=lambda t: ['TOTAL', t['count'], f"{t['amount']:.2f}", ''],
    )
    _make_report_routes(
        'bank-charges-by-account',
        data_fn=_service_fn(bank_charges_by_account),
        csv_columns=['Account', 'Last 4', 'Charge Count', 'Total Charges', 'Avg / Charge'],
        csv_row_fn=lambda r: [r['account'], r['last4'], r['count'], f"{r['amount']:.2f}", f"{r['avg']:.2f}"],
    )
    _make_report_routes(
        'period-comparison',
        data_fn=_service_fn(period_comparison),
        csv_columns=lambda t: ['Metric', t['current_label'], t['prior_label'], 'Delta', '% Change'],
        csv_row_fn=lambda r: [r['label'], f"{r['current']:.2f}" if r['is_money'] else f"{int(r['current'])}", f"{r['prior']:.2f}" if r['is_money'] else f"{int(r['prior'])}", f"{r['delta']:.2f}" if r['is_money'] else f"{int(r['delta'])}", f"{r['pct']:+.1f}%"],
        extra_args_fn=lambda: _parse_compare_dates(request.args),
    )
    _make_report_routes(
        'fees-vs-tax',
        data_fn=_service_fn(fees_vs_tax),
        csv_columns=['Line', 'Amount'],
        csv_row_fn=lambda r: [r['label'], f"{r['amount']:.2f}"],
        csv_totals_fn=lambda t: ['Tax / Fee Ratio', f"{t['ratio']:.2f}"],
    )

    # Shadow-register every /reports/<slug>.csv on /owner/reports/<slug>.csv.
    # Scope flips inside the handler via _report_scope_ids().
    for rule in list(app.url_map.iter_rules()):
        if not rule.rule.startswith("/reports/"):
            continue
        ep = rule.endpoint
        if not ep.startswith("report_"):
            continue
        owner_ep = "owner_" + ep
        if owner_ep in app.view_functions:
            continue
        wrapped = app.view_functions[ep]
        original = getattr(wrapped, "__wrapped__", wrapped)
        owner_path = "/owner" + rule.rule
        app.add_url_rule(owner_path, endpoint=owner_ep,
                         view_func=original,
                         methods=list(rule.methods - {"HEAD", "OPTIONS"}))

    # ── Superadmin reports ────────────────────────────────────
    _make_superadmin_report_routes(
        'active-stores-by-plan',
        data_fn=_sa_service_fn(active_stores_by_plan),
        csv_columns=['Plan', 'Stores'],
        csv_row_fn=lambda r: [r['plan'], r['count']],
        csv_totals_fn=lambda t: ['TOTAL', t['count']],
        csv_fname_prefix='active-stores-by-plan',
    )
    _make_superadmin_report_routes(
        'signup-funnel',
        data_fn=_sa_service_fn(signup_funnel),
        csv_columns=['Plan', 'Signups'],
        csv_row_fn=lambda r: [r['plan'], r['count']],
        csv_totals_fn=lambda t: ['TOTAL', t['count']],
    )
    _make_superadmin_report_routes(
        'login-activity',
        data_fn=_sa_service_fn(login_activity),
        csv_columns=['Role', 'Active Users'],
        csv_row_fn=lambda r: [r['role'], r['count']],
        csv_totals_fn=lambda t: ['TOTAL', t['count']],
    )
    _make_superadmin_report_routes(
        'mrr-arr',
        data_fn=_sa_service_fn(mrr_arr),
        csv_columns=['Plan', 'Cycle', 'Stores', 'MRR', 'ARR'],
        csv_row_fn=lambda r: [r['plan'], r['cycle'], r['stores'], f"{r['mrr']:.2f}", f"{r['arr']:.2f}"],
        csv_totals_fn=lambda t: ['TOTAL', '', t['stores'], f"{t['mrr']:.2f}", f"{t['arr']:.2f}"],
    )
    _make_superadmin_report_routes(
        'churn-cohort',
        data_fn=_sa_service_fn(churn_cohort),
        csv_columns=['Cohort', 'Cancelled', 'Still Active', 'Churn %'],
        csv_row_fn=lambda r: [r['cohort'], r['cancelled'], r['active'], f"{r['churn_pct']:.1f}%"],
    )
    _make_superadmin_report_routes(
        'conversion-rate',
        data_fn=_sa_service_fn(conversion_rate),
        csv_columns=['Status', 'Stores'],
        csv_row_fn=lambda r: [r['label'], r['count']],
        csv_totals_fn=lambda t: ['TOTAL', t['total']],
    )
    _make_superadmin_report_routes(
        'time-to-convert',
        data_fn=_sa_service_fn(time_to_convert),
        csv_columns=['Slug', 'Name', 'Plan', 'Signed Up', 'Days Active'],
        csv_row_fn=lambda r: [r['slug'], r['name'], r['plan'], r['signed_up'].isoformat(), r['days']],
    )
    _make_superadmin_report_routes(
        'trial-expiry-timing',
        data_fn=_sa_service_fn(trial_expiry_timing),
        csv_columns=['Bucket', 'Stores'],
        csv_row_fn=lambda r: [r['bucket'], r['count']],
    )
    _make_superadmin_report_routes(
        'bank-sync-adoption',
        data_fn=_sa_service_fn(bank_sync_adoption),
        csv_columns=['Plan', 'Connected', 'Total', 'Adoption %'],
        csv_row_fn=lambda r: [r['plan'], r['connected'], r['total'], f"{r['rate_pct']:.1f}%"],
    )
    _make_superadmin_report_routes(
        'tv-display-adoption',
        data_fn=_sa_service_fn(tv_display_adoption),
        csv_columns=['Slug', 'Name', 'Plan'],
        csv_row_fn=lambda r: [r['slug'], r['name'], r['plan']],
    )
    _make_superadmin_report_routes(
        'owner-adoption',
        data_fn=_sa_service_fn(owner_adoption),
        csv_columns=['Owner', 'Email', 'Linked Stores'],
        csv_row_fn=lambda r: [r['owner'], r['email'], r['stores']],
    )
    _make_superadmin_report_routes(
        'passkey-adoption',
        data_fn=_sa_service_fn(passkey_adoption),
        csv_columns=['Role', 'Users with Passkey'],
        csv_row_fn=lambda r: [r['role'], r['count']],
    )
    _make_superadmin_report_routes(
        'password-resets',
        data_fn=_sa_service_fn(password_resets),
        csv_columns=['Created', 'Username', 'Role', 'Status'],
        csv_row_fn=lambda r: [r['created_at'].isoformat() if r['created_at'] else '', r['username'], r['role'], r['status']],
    )
    _make_superadmin_report_routes(
        'suspended-stores',
        data_fn=_sa_service_fn(suspended_stores),
        csv_columns=['Slug', 'Name', 'Plan', 'Reason'],
        csv_row_fn=lambda r: [r['slug'], r['name'], r['plan'], r['reason']],
    )
    _make_superadmin_report_routes(
        'retention-queue',
        data_fn=_sa_service_fn(retention_queue),
        csv_columns=['Slug', 'Name', 'Plan', 'Purge Date', 'Days Left'],
        csv_row_fn=lambda r: [r['slug'], r['name'], r['plan'], r['until'].isoformat() if r['until'] else '', r['days_left']],
    )
    _make_superadmin_report_routes(
        'refunds',
        data_fn=_sa_service_fn(refunds),
        csv_columns=['Reason', 'Count', 'Amount'],
        csv_row_fn=lambda r: [r['reason'], r['count'], f"{r['amount']:.2f}"],
        csv_totals_fn=lambda t: ['TOTAL', t['count'], f"{t['amount']:.2f}"],
    )
    _make_superadmin_report_routes(
        'failed-payments',
        data_fn=_sa_service_fn(failed_payments),
        csv_columns=['Reason', 'Count', 'Amount'],
        csv_row_fn=lambda r: [r['reason'], r['count'], f"{r['amount']:.2f}"],
        csv_totals_fn=lambda t: ['TOTAL', t['count'], f"{t['amount']:.2f}"],
    )
    _make_superadmin_report_routes(
        'payouts',
        data_fn=_sa_service_fn(payouts),
        csv_columns=['Payout ID', 'Amount', 'Status', 'Method', 'Arrival'],
        csv_row_fn=lambda r: [r['id'], f"{r['amount']:.2f}", r['status'], r['method'], r['arrival'].isoformat() if r['arrival'] else ''],
        csv_totals_fn=lambda t: ['TOTAL', f"{t['amount']:.2f}", '', '', ''],
    )
    _make_superadmin_report_routes(
        'dau-mau',
        data_fn=_sa_service_fn(dau_mau),
        csv_columns=['Date', 'Active Users'],
        csv_row_fn=lambda r: [str(r['day']), r['users']],
        csv_totals_fn=lambda t: ['TOTAL (MAU)', t['mau']],
    )
    _make_superadmin_report_routes(
        'webhook-health',
        data_fn=_sa_service_fn(webhook_health),
        csv_columns=['Status', 'Count'],
        csv_row_fn=lambda r: [r['status'], r['count']],
        csv_totals_fn=lambda t: ['TOTAL', t['count']],
    )
