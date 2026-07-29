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
from api.Core.Clock import utc_now


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
    if store is None:
        return False
    return str(store.plan) in _PAID_PLAN_NAMES


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
    delta = store.data_retention_until - utc_now()
    return int(max(0, delta.days))


# Gate reasons returned by ``store_gate_status``. Ordered by
# precedence — a frozen store reports "frozen" even if its plan also
# lapsed, because the operator suspension is the more specific state.
GATE_REASON_FROZEN = "frozen"          # superadmin suspended the store
GATE_REASON_SUBSCRIPTION = "subscription"  # trial/grace fully elapsed or plan inactive
GATE_REASON_NONE = ""                   # store is usable


def store_gate_status(store: Store | None) -> dict[str, object]:
    """Whether a store's users should be gated out of the app, and why.

    Returns ``{"gated": bool, "reason": str}`` where ``reason`` is one of
    ``GATE_REASON_FROZEN`` / ``GATE_REASON_SUBSCRIPTION`` / ``""``.

    Precedence:
      1. ``frozen_at`` set  → gated, reason="frozen" (superadmin
         suspension; re-subscribing does NOT lift it).
      2. ``get_trial_status(store) == "expired"`` → gated,
         reason="subscription" (trial + grace fully elapsed, OR
         plan == "inactive"). Self-serve re-subscribe clears it.
      3. otherwise → not gated. A store in trial / grace / paid keeps
         full access; grace is deliberately NOT gated so a lapsing
         operator still gets the reduced-functionality window.

    A ``None`` store (superadmin — no store scope) is never gated.

    Pure read — no DB writes.
    """
    if store is None:
        return {"gated": False, "reason": GATE_REASON_NONE}
    if getattr(store, "frozen_at", None) is not None:
        return {"gated": True, "reason": GATE_REASON_FROZEN}
    # Local import avoids a module-load cycle (trial imports Billing.Models,
    # which this Service also depends on).
    from api.Modules.Billing.Services.trial import get_trial_status
    if get_trial_status(store) == "expired":
        return {"gated": True, "reason": GATE_REASON_SUBSCRIPTION}
    return {"gated": False, "reason": GATE_REASON_NONE}
