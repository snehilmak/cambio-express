"""Superadmin — Services."""
from api.Modules.Superadmin.Services.anomalies import (
    ANOMALY_OVERSHORT_HIGH_THRESHOLD,
    ANOMALY_OVERSHORT_LOOKBACK_DAYS,
    ANOMALY_OVERSHORT_MEDIUM_THRESHOLD,
    ANOMALY_QUIET_LOOKBACK_ACTIVE_DAYS,
    ANOMALY_QUIET_LOOKBACK_QUIET_DAYS,
    ANOMALY_QUIET_MIN_PRIOR_TRANSFERS,
    big_over_short_anomalies,
    compute_platform_anomalies,
    quiet_store_anomalies,
)
from api.Modules.Superadmin.Services.dashboard import (
    compute_mrr,
    superadmin_dashboard_context,
)
from api.Modules.Superadmin.Services.reports import (
    PLAN_MRR,
    active_stores_by_plan,
    churn_cohort,
    conversion_rate,
    login_activity,
    mrr_arr,
    signup_funnel,
    time_to_convert,
    trial_expiry_timing,
)

__all__ = [
    "ANOMALY_OVERSHORT_HIGH_THRESHOLD",
    "ANOMALY_OVERSHORT_LOOKBACK_DAYS",
    "ANOMALY_OVERSHORT_MEDIUM_THRESHOLD",
    "ANOMALY_QUIET_LOOKBACK_ACTIVE_DAYS",
    "ANOMALY_QUIET_LOOKBACK_QUIET_DAYS",
    "ANOMALY_QUIET_MIN_PRIOR_TRANSFERS",
    "PLAN_MRR",
    "active_stores_by_plan",
    "big_over_short_anomalies",
    "churn_cohort",
    "compute_mrr",
    "compute_platform_anomalies",
    "conversion_rate",
    "login_activity",
    "mrr_arr",
    "quiet_store_anomalies",
    "signup_funnel",
    "superadmin_dashboard_context",
    "time_to_convert",
    "trial_expiry_timing",
]
