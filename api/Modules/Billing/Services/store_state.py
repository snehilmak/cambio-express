"""Store-level subscription-state helpers.

Pure-function reads on a `Store` row. Used widely in templates +
chrome rendering + auth gates, so they live in the Service layer
to keep the contract consistent across surfaces.

Migrated from `app.py`:
- `store_addon_keys` → `store_addon_keys`
- `store_has_paid_plan` → `store_has_paid_plan`
- `data_retention_days_left` → `data_retention_days_left`
"""
from datetime import datetime

from api.Modules.Billing.Models import Store


# Roles considered "paid" for feature gating. Trial / inactive don't
# qualify; basic + pro tiers do. Yearly variants share the base
# tier name on Store.plan, so this set is stable regardless of
# billing cycle.
_PAID_PLAN_NAMES = ("basic", "pro")


def store_addon_keys(store: Store | None) -> set[str]:
    """Return the set of add-on keys currently active for a store.

    Add-ons are stored as a comma-separated string on `Store.addons`
    so they can be edited by hand without an extra table. Empty
    entries (from trailing commas) are filtered out.
    """
    if not store or not store.addons:
        return set()
    return {k.strip() for k in store.addons.split(",") if k.strip()}


def store_has_paid_plan(store: Store | None) -> bool:
    """True iff `store` is on a paid subscription tier (basic / pro).

    None / trial / inactive all return False. Used by feature gates
    (referrals page, paid-only reports, etc.) to keep the contract
    in one place.
    """
    return bool(store) and store.plan in _PAID_PLAN_NAMES


def data_retention_days_left(store: Store | None) -> int | None:
    """Days until cancelled-store data is purged.

    Returns None when no retention timer is scheduled (active
    subscription, trial, or never-cancelled). Returns 0 when the
    timer has already elapsed (the purge cron will catch it on the
    next run). Always non-negative — the chrome shows
    "Cancelled, data purges in N days" and N=0 is a valid display
    state for the day-of-purge.
    """
    if not store or not store.data_retention_until:
        return None
    delta = store.data_retention_until - datetime.utcnow()
    return max(0, delta.days)
