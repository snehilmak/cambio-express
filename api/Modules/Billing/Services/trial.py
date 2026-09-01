"""Trial-status calculation.

Pure function returning the store's current trial state. Used by:
- Login redirect logic (trial-expired admins land on /subscribe)
- Banner / chrome rendering (the "trial ends in N days" message)
- The send-trial-reminders cron filter
- The purge-expired-stores guard

Single source of truth so the trial-state contract stays consistent
across all those surfaces.
"""
from datetime import timedelta

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


def trial_days_left(store: Store | None) -> int | None:
    """Whole days until ``trial_ends_at``, or None when the store
    isn't on a running trial.

    Rounds UP: with 30 hours left an operator should read "2 days",
    not "1" — a countdown that undersells the time it is describing
    reads as a bug the first time someone checks a calendar.

    0 means the trial ends today. Past the end it returns None; the
    store is in grace or expired and the chrome has a different
    thing to say.
    """
    if store is None or store.plan not in ("trial",):
        return None
    if store.trial_ends_at is None:
        return None
    remaining = store.trial_ends_at - utc_now()
    if remaining.total_seconds() <= 0:
        return None
    return int(-(-remaining.total_seconds() // 86400))


def trial_banner(store: Store | None) -> dict[str, object] | None:
    """What the chrome should say about this store's subscription,
    or None when there is nothing to say (paid, or no trial).

    Returned to every authed SPA load so the topbar can show a
    countdown for the WHOLE trial rather than appearing on day 4 —
    "5 days left" on day two sets an expectation, while something
    that materialises near the end reads as an alarm.

    ``tone`` escalates at EXPIRING_SOON_THRESHOLD_DAYS, reusing the
    same threshold the status machine and the reminder cron already
    use, so the three never disagree about when to start nagging.
    """
    status = get_trial_status(store)
    if status in ("exempt",):
        return None
    days = trial_days_left(store)
    if status == "active" or status == "expiring_soon":
        if days is None:
            return None
        return {
            "status": status,
            "days_left": days,
            "tone": (
                "warning" if status == "expiring_soon" else "neutral"
            ),
            "message": (
                "Your free trial ends today."
                if days == 0 else
                f"{days} day{'s' if days != 1 else ''} left in your "
                "free trial."
            ),
        }
    if status == "grace":
        return {
            "status": status,
            "days_left": 0,
            "tone": "negative",
            "message": (
                "Your free trial has ended — you can still view and "
                "export your data, but not add to it."
            ),
        }
    return {
        "status": status,
        "days_left": 0,
        "tone": "negative",
        "message": "Your subscription has lapsed.",
    }
