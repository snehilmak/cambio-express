"""Subscription cancellation Service.

Pure-function helpers for the subscription-cancellation +
return-customer reactivation paths.

Two flows:
  - Stripe `customer.subscription.deleted` webhook → mark store
    inactive + start the retention timer.
  - Stripe `checkout.session.completed` webhook (returning
    customer) → clear the retention timer + cancellation timestamp
    so the store reactivates cleanly.

Per CLAUDE.md invariant #4: data retention timer is 180 days.
The store retains its DB rows for that window; the
`flask purge-expired-stores` CLI deletes them when the timer expires.
"""
from datetime import timedelta

from sqlalchemy.orm import Session

from api.Modules.Billing.Models import Store
from api.Core.Clock import utc_now


# Default retention window after a paid subscription is cancelled.
# Mirrors the legacy `DATA_RETENTION_DAYS` module constant.
DEFAULT_RETENTION_DAYS = 180


def find_store_by_subscription_id(
    db: Session, subscription_id: str,
) -> Store | None:
    """Look up the Store that owns a given Stripe subscription_id.
    Returns None when no Store matches (e.g. a webhook for a
    subscription created in a sandbox that hasn't synced)."""
    if not subscription_id:
        return None
    return (
        db.query(Store)
          .filter(Store.stripe_subscription_id == subscription_id)
          .first()
    )


def apply_subscription_cancelled(
    store: Store, *, retention_days: int = DEFAULT_RETENTION_DAYS,
) -> None:
    """Mark `store` as cancelled. Sets:
      - plan = "inactive"
      - billing_cycle = ""
      - stripe_subscription_id = ""
      - canceled_at = now
      - data_retention_until = now + retention_days

    Caller commits.

    Idempotent — and the retention clock counts from the FIRST
    cancellation. Stripe retries `customer.subscription.deleted`
    aggressively (any non-2xx, plus periodic redelivery), so a naive
    re-stamp would push `data_retention_until` forward on every
    duplicate: a store cancelled 170 days ago would get a fresh
    180-day window each time Stripe re-sends, and the purge cron
    would never catch it. We therefore only stamp `canceled_at` +
    `data_retention_until` while the clock isn't already running
    (`data_retention_until is None`). A returning customer runs
    `clear_cancellation_state()` which resets it to None, so a later
    re-cancel stamps a fresh window correctly. The terminal plan /
    billing fields are always re-applied (harmless when repeated).
    """
    store.plan = "inactive"
    store.billing_cycle = ""
    store.stripe_subscription_id = ""
    if store.data_retention_until is None:
        now = utc_now()
        store.canceled_at = now
        store.data_retention_until = now + timedelta(days=retention_days)


def clear_cancellation_state(store: Store) -> None:
    """Returning-customer reset: clear `canceled_at` +
    `data_retention_until` so the purge job ignores the store, and
    reset the trial-reminder dedup flag so future reminders fire
    fresh.

    Called from the `checkout.session.completed` handler after the
    plan + Stripe IDs are stamped. Caller commits.
    """
    store.canceled_at = None
    store.data_retention_until = None
    # Reset the trial-reminder dedup flag too, so if this
    # subscription later lapses and a NEW trial ever begins,
    # the reminder cron sends fresh instead of no-oping.
    store.trial_reminder_sent_at = None
