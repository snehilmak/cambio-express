"""Trial-status calculation.

Pure function returning the store's current trial state. Used by:
- Login redirect logic (trial-expired admins land on /subscribe)
- Banner / chrome rendering (the "trial ends in N days" message)
- The send-trial-reminders cron filter
- The purge-expired-stores guard

Single source of truth so the trial-state contract stays consistent
across all those surfaces.
"""
from datetime import datetime, timedelta

from api.Modules.Billing.Models import Store
from api.Core.Clock import utc_now


# Days before trial_ends_at at which we start nagging the operator.
EXPIRING_SOON_THRESHOLD_DAYS = 3


def get_trial_status(store: Store | None) -> str:
    """Compute the trial-state label for `store`.

    Returns one of:
      "exempt"          — store has paid plan OR no trial timestamps
                          (None store, or a paid store, or a legacy
                          row that was never given a trial window).
      "active"          — trial is in progress, > 3 days remaining.
      "expiring_soon"   — trial ends in ≤ 3 days; banners go red.
      "grace"           — trial_ends_at has passed but grace_ends_at
                          hasn't; store still works but with reduced
                          functionality.
      "expired"         — store.plan == "inactive" OR grace_ends_at
                          has elapsed; store is read-only-ish.

    The function is a pure read — no DB writes, no side effects.
    """
    if store is None:
        return "exempt"
    if store.plan in ("basic", "pro"):
        return "exempt"
    if store.plan == "inactive":
        return "expired"
    if store.trial_ends_at is None:
        return "exempt"
    now = utc_now()
    if store.grace_ends_at is not None and now >= store.grace_ends_at:
        return "expired"
    if now >= store.trial_ends_at:
        return "grace"
    if now >= store.trial_ends_at - timedelta(
        days=EXPIRING_SOON_THRESHOLD_DAYS,
    ):
        return "expiring_soon"
    return "active"
