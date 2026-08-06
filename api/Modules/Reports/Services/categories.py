"""Report Center taxonomy + URL resolution.

Two data tables + two pure helpers:

  - :data:`REPORT_CATEGORIES` — admin / owner Report Center
    (``/app/reports`` + ``/app/owner/reports``).
  - :data:`SUPERADMIN_REPORT_CATEGORIES` — superadmin BI surface
    (``/app/superadmin/reports``).
  - :func:`url_from_endpoint(name)` — derives the public SPA URL
    from the report's slug-style endpoint name (e.g.
    ``report_sales_by_company`` → ``/reports/sales-by-company``).
  - :func:`resolved_categories(registry, endpoint_prefix="")` —
    walks a registry, fills in each entry's ``url`` + ``status``
    fields so the React Report Center can render directly.

Pure — no DB / framework / context dependency.
"""
from __future__ import annotations

from typing import Any


REPORT_CATEGORIES: list[dict[str, Any]] = [
    {
        "key":   "sales",
        "label": "Sales",
        "icon":  '<svg viewBox="0 0 24 24" stroke="currentColor" fill="none" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="12" y1="20" x2="12" y2="10"/><line x1="18" y1="20" x2="18" y2="4"/><line x1="6" y1="20" x2="6" y2="16"/></svg>',
        "reports": [
            {"key": "sales_by_company",
             "label": "Sales by Company",
             "description": "Volume, fees, and federal tax split between Intermex, Maxi, and Barri.",
             "endpoint": "report_sales_by_company"},
            {"key": "sales_by_service",
             "label": "Sales by Service Type",
             "description": "Money Transfer vs. Bill Payment vs. Top Up vs. Recharge — volume and count.",
             "endpoint": "report_sales_by_service_type"},
            {"key": "sales_by_employee",
             "label": "Sales by Employee",
             "description": "Per-employee transfer count and total volume.",
             "endpoint": "report_sales_by_employee"},
            {"key": "cashier_productivity",
             "label": "Cashier Productivity",
             "description": "Volume + count per cashier on duty (the 'Processed by' selection on each transfer).",
             "endpoint": "report_cashier_productivity"},
            {"key": "top_customers",
             "label": "Top Customers by Volume",
             "description": "Senders who moved the most in the period.",
             "endpoint": "report_top_customers"},
        ],
    },
    {
        "key":   "financial",
        "label": "Financial",
        "icon":  '<svg viewBox="0 0 24 24" stroke="currentColor" fill="none" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="12" y1="1" x2="12" y2="23"/><path d="M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"/></svg>',
        "reports": [
            {"key": "period_pl",
             "label": "Period P&L",
             "description": "Income, expenses, and net income aggregated for any date range.",
             "endpoint": "report_period_pl"},
            {"key": "ach_volume",
             "label": "ACH Volume",
             "description": "Daily ACH batches and totals per remittance company.",
             "endpoint": "report_ach_volume"},
            {"key": "bank_charges",
             "label": "Bank Charges by Account",
             "description": "Per-account charges aggregated for the period.",
             "endpoint": "report_bank_charges_by_account"},
            {"key": "period_comparison",
             "label": "Period Comparison",
             "description": "Side-by-side metrics vs. the prior period of the same length.",
             "endpoint": "report_period_comparison"},
            {"key": "fees_vs_tax",
             "label": "Fees vs. Federal Tax",
             "description": "Store revenue (fees) vs. ACH-bound federal tax.",
             "endpoint": "report_fees_vs_tax"},
        ],
    },
    {
        "key":   "operations",
        "label": "Operations",
        "icon":  '<svg viewBox="0 0 24 24" stroke="currentColor" fill="none" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/></svg>',
        "reports": [
            {"key": "returned_checks_status",
             "label": "Returned Check Status",
             "description": "Open, recovered, and lost returned checks for a period.",
             "endpoint": "report_returned_check_status"},
            {"key": "bank_txn_breakdown",
             "label": "Bank Transactions Breakdown",
             "description": "Synced bank-feed rows summarised by category.",
             "endpoint": "report_bank_txn_breakdown"},
            {"key": "daily_drops",
             "label": "Daily Drops",
             "description": "Cash drops by day across the period.",
             "endpoint": "report_daily_drops"},
            {"key": "check_deposits",
             "label": "Check Deposits",
             "description": "Deposit log totalled by day across the period.",
             "endpoint": "report_check_deposits"},
        ],
    },
    {
        "key":   "customers",
        "label": "Customers",
        "icon":  '<svg viewBox="0 0 24 24" stroke="currentColor" fill="none" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>',
        "reports": [
            {"key": "top_senders",
             "label": "Top Senders",
             "description": "Most-active senders by transaction count.",
             "endpoint": "report_top_senders"},
            {"key": "top_recipients",
             "label": "Top Recipients",
             "description": "Most-paid recipients across all senders.",
             "endpoint": "report_top_recipients"},
            {"key": "by_country",
             "label": "By Destination Country",
             "description": "Volume + count grouped by recipient country.",
             "endpoint": "report_by_destination_country"},
            {"key": "new_vs_returning",
             "label": "New vs. Returning Senders",
             "description": "First-time senders against repeat customers in the period.",
             "endpoint": "report_new_vs_returning"},
        ],
    },
    {
        "key":   "audit",
        "label": "Audit",
        "icon":  '<svg viewBox="0 0 24 24" stroke="currentColor" fill="none" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="9" y1="13" x2="15" y2="13"/><line x1="9" y1="17" x2="13" y2="17"/></svg>',
        "reports": [
            {"key": "high_value_transfers",
             "label": "High-Value Transfers",
             "description": "Transfers above a configurable threshold (default $3,000).",
             "endpoint": "report_high_value_transfers"},
            {"key": "employee_activity",
             "label": "Employee Activity",
             "description": "Per-employee transfers, totals, cancelled count, and last activity.",
             "endpoint": "report_employee_activity"},
            {"key": "bank_rule_audit",
             "label": "Bank-Rule Audit Log",
             "description": "Which rule auto-categorised which transaction.",
             "endpoint": "report_bank_rule_audit"},
            {"key": "cancelled_transfers",
             "label": "Cancelled Transfers",
             "description": "Transfers cancelled or rejected within the period.",
             "endpoint": "report_cancelled_transfers"},
        ],
    },
]


SUPERADMIN_REPORT_CATEGORIES: list[dict[str, Any]] = [
    {
        "key":   "platform_health",
        "label": "Platform Health",
        "icon":  '<svg viewBox="0 0 24 24" stroke="currentColor" fill="none" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 12h-4l-3 9L9 3l-3 9H2"/></svg>',
        "reports": [
            {"key": "dau_mau",
             "label": "Daily / Monthly Actives",
             "description": "DAU + MAU per day from the LoginEvent feed, plus stickiness.",
             "endpoint": "superadmin_report_dau_mau"},
            {"key": "active_stores_by_plan",
             "label": "Active Stores by Plan",
             "description": "Headcount across trial / basic / pro / inactive.",
             "endpoint": "superadmin_report_active_stores_by_plan"},
            {"key": "signup_funnel",
             "label": "Signup Funnel",
             "description": "Stores created in the period bucketed by current plan.",
             "endpoint": "superadmin_report_signup_funnel"},
            {"key": "login_activity",
             "label": "Login Activity",
             "description": "Per-role sign-in counts in the period.",
             "endpoint": "superadmin_report_login_activity"},
        ],
    },
    {
        "key":   "revenue",
        "label": "Revenue",
        "icon":  '<svg viewBox="0 0 24 24" stroke="currentColor" fill="none" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="12" y1="1" x2="12" y2="23"/><path d="M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"/></svg>',
        "reports": [
            {"key": "mrr_arr",
             "label": "MRR / ARR",
             "description": "Recurring revenue split by plan and billing cycle.",
             "endpoint": "superadmin_report_mrr_arr"},
            {"key": "churn",
             "label": "Churn Cohort",
             "description": "Customer churn by signup cohort.",
             "endpoint": "superadmin_report_churn_cohort"},
            {"key": "refunds",
             "label": "Refunds",
             "description": "Stripe refunds in the period grouped by reason.",
             "endpoint": "superadmin_report_refunds"},
        ],
    },
    {
        "key":   "stripe",
        "label": "Stripe",
        "icon":  '<svg viewBox="0 0 24 24" stroke="currentColor" fill="none" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="5" width="20" height="14" rx="2"/><line x1="2" y1="10" x2="22" y2="10"/></svg>',
        "reports": [
            {"key": "webhook_health",
             "label": "Webhook Health",
             "description": "Inbound Stripe webhook deliveries by status.",
             "endpoint": "superadmin_report_webhook_health"},
            {"key": "failed_payments",
             "label": "Failed Payments",
             "description": "Recent failed charges grouped by reason.",
             "endpoint": "superadmin_report_failed_payments"},
            {"key": "payouts",
             "label": "Payouts",
             "description": "Stripe payouts to the platform bank account.",
             "endpoint": "superadmin_report_payouts"},
        ],
    },
    {
        "key":   "trial",
        "label": "Trial Funnel",
        "icon":  '<svg viewBox="0 0 24 24" stroke="currentColor" fill="none" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>',
        "reports": [
            {"key": "conversion_rate",
             "label": "Conversion Rate",
             "description": "Trial → paid percentage for cohorts that signed up in the period.",
             "endpoint": "superadmin_report_conversion_rate"},
            {"key": "time_to_convert",
             "label": "Time to Convert",
             "description": "Per-store days from signup to today (paid stores only).",
             "endpoint": "superadmin_report_time_to_convert"},
            {"key": "trial_expiry_timing",
             "label": "Trial Expiry Timing",
             "description": "Where in their trial window each store sits at end of period.",
             "endpoint": "superadmin_report_trial_expiry_timing"},
        ],
    },
    {
        "key":   "feature_adoption",
        "label": "Feature Adoption",
        "icon":  '<svg viewBox="0 0 24 24" stroke="currentColor" fill="none" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>',
        "reports": [
            {"key": "bank_sync_adoption",
             "label": "Bank Sync Adoption",
             "description": "Stores that have connected at least one account, by plan.",
             "endpoint": "superadmin_report_bank_sync_adoption"},
            {"key": "tv_display_adoption",
             "label": "TV Display Add-on",
             "description": "Active TV-display installations by store.",
             "endpoint": "superadmin_report_tv_display_adoption"},
            {"key": "owner_adoption",
             "label": "Multi-store Owners",
             "description": "Owner accounts linked to more than one store.",
             "endpoint": "superadmin_report_owner_adoption"},
            {"key": "passkey_adoption",
             "label": "Passkey Adoption",
             "description": "Users with at least one registered passkey, by role.",
             "endpoint": "superadmin_report_passkey_adoption"},
        ],
    },
    {
        "key":   "support",
        "label": "Support / Audit",
        "icon":  '<svg viewBox="0 0 24 24" stroke="currentColor" fill="none" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="9" y1="13" x2="15" y2="13"/><line x1="9" y1="17" x2="13" y2="17"/></svg>',
        "reports": [
            {"key": "audit_log",
             "label": "Superadmin Audit Log",
             "description": "Every superadmin mutation, with target and actor.",
             # SPA route WITHOUT the /app basename — the Report Center
             # renders report links via react-router `to`, which adds
             # the /app basename itself. (A literal `/app/...` here
             # would double to `/app/app/...`.)
             "url": "/superadmin/audit-log"},
            {"key": "password_resets",
             "label": "Password Resets",
             "description": "Reset-token activity in the period (used / expired / open).",
             "endpoint": "superadmin_report_password_resets"},
            {"key": "suspended_stores",
             "label": "Suspended / Inactive Stores",
             "description": "Stores currently suspended (is_active=False) or marked inactive.",
             "endpoint": "superadmin_report_suspended_stores"},
            {"key": "retention_queue",
             "label": "Retention Queue",
             "description": "Stores in the 180-day data-retention delete window.",
             "endpoint": "superadmin_report_retention_queue"},
        ],
    },
]


# ── Admin-store-only Report Center entries ──────────────────
#
# These surface pages that live OUTSIDE the /reports drilldown family
# (the month-keyed P&L, the operator audit log, the CSV export
# catalog) inside the store admin's Report Center, so "Reports" is the
# single place to find everything. They carry literal SPA `url`s
# (no /app basename — the React Report Center adds it via `to`).
#
# Injected ONLY into the admin store index (endpoint_prefix="") by
# `with_admin_store_extras`. The owner umbrella index
# (endpoint_prefix="owner_") must NOT include them — those are
# store-scoped routes an owner viewing the umbrella has no use for.

ADMIN_MONTHLY_PL_REPORT: dict[str, Any] = {
    "key": "monthly_pl",
    "label": "Monthly P&L",
    "description": "Full profit & loss for a single month — income, expenses, and net.",
    "url": "/monthly",
}

ADMIN_LOGS_EXPORTS_CATEGORY: dict[str, Any] = {
    "key":   "logs_exports",
    "label": "Logs & Exports",
    "icon":  '<svg viewBox="0 0 24 24" stroke="currentColor" fill="none" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>',
    "reports": [
        {"key": "audit_log",
         "label": "Audit log",
         "description": "Who changed what, and when — the store's operator audit trail.",
         "url": "/admin/audit-log"},
        {"key": "data_export",
         "label": "Data export",
         "description": "Download CSV / ZIP snapshots of your store's data.",
         "url": "/admin/data-export"},
    ],
}


def with_admin_store_extras(
    registry: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Return a shallow copy of the admin report registry with the
    store-only entries injected: Monthly P&L prepended to the
    Financial category, plus a trailing Logs & Exports category.

    Admin store index (``/reports``) only — do NOT call this for the
    owner umbrella index, which must stay free of store-scoped routes.
    Non-mutating: the input registry is left untouched."""
    out: list[dict[str, Any]] = []
    for cat in registry:
        if cat.get("key") == "financial":
            out.append({
                **cat,
                "reports": [ADMIN_MONTHLY_PL_REPORT, *cat["reports"]],
            })
        else:
            out.append(cat)
    out.append(ADMIN_LOGS_EXPORTS_CATEGORY)
    return out


def url_from_endpoint(endpoint: str) -> str | None:
    """Convention-based reverse of the report-route endpoint names.

      ``report_<slug_underscored>``            → ``/reports/<slug>``
      ``owner_report_<slug_underscored>``      → ``/owner/reports/<slug>``
      ``superadmin_report_<slug_underscored>`` → ``/superadmin/reports/<slug>``

    Returns None for names that don't match the convention so the
    Report Center can flag those as ``coming_soon``.
    """
    if endpoint.startswith("owner_report_"):
        slug = endpoint[len("owner_report_"):].replace("_", "-")
        return f"/owner/reports/{slug}"
    if endpoint.startswith("superadmin_report_"):
        slug = endpoint[len("superadmin_report_"):].replace("_", "-")
        return f"/superadmin/reports/{slug}"
    if endpoint.startswith("report_"):
        slug = endpoint[len("report_"):].replace("_", "-")
        return f"/reports/{slug}"
    return None


def resolved_categories(registry: list[dict[str, Any]], endpoint_prefix: str = "") -> list[dict[str, Any]]:
    """Return ``registry`` with each report enriched with a rendered
    URL plus a ``status`` flag the template uses to swap between
    "View" button and "Coming soon" pill.

    URL derivation order:
      1. Literal ``url`` on the registry entry (wins outright).
      2. ``url_from_endpoint(endpoint)`` — convention-based.
      3. None → status='coming_soon'.

    ``endpoint_prefix`` lets the owner Report Center reuse the
    admin registry while routing to owner-prefixed mirrors (every
    ``report_<x>`` admin endpoint maps to ``owner_report_<x>``).
    """
    out = []
    for cat in registry:
        reports = []
        for r in cat["reports"]:
            ep = r.get("endpoint")
            url = r.get("url")  # literal URL takes precedence
            if not url and ep:
                effective_ep = ep
                if endpoint_prefix and not ep.startswith(endpoint_prefix):
                    effective_ep = endpoint_prefix + ep
                url = url_from_endpoint(effective_ep)
            reports.append({
                **r,
                "url": url,
                "status": "ready" if url else "coming_soon",
            })
        out.append({**cat, "reports": reports})
    return out


__all__ = [
    "REPORT_CATEGORIES",
    "SUPERADMIN_REPORT_CATEGORIES",
    "resolved_categories",
    "url_from_endpoint",
]
