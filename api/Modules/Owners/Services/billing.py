"""Owner billing rollup — every store's subscription state in one
place.

Subscriptions are per-store (owner decision, 2026-08-28: no single
quantity-based owner subscription), which is fine for Stripe but
leaves the multi-store owner with no way to answer "what am I paying
in total, and is anything about to lapse?" without switching into
each store and opening its subscription page.

This Service answers that in one read: a row per store with plan,
trial state, monthly cost and whatever needs attention, plus totals
across the umbrella.  It is deliberately READ-ONLY — acting on a
store (subscribe, open the Stripe portal) still happens inside that
store, where Stripe's customer + subscription live.
"""
from typing import Any, TypedDict

from sqlalchemy.orm import Session

from api.Core.Clock import utc_now


class OwnerBillingStore(TypedDict):
    store_id: int
    store_name: str
    store_slug: str
    plan: str
    plan_label: str
    plan_price_label: str
    billing_cycle: str
    monthly_cost: float
    trial_status: str
    trial_days_left: int | None
    trial_ends_at: str | None
    retention_days_left: int | None
    addon_count: int
    addon_monthly_cost: float
    has_paid_plan: bool
    attention: str


class OwnerBillingTotals(TypedDict):
    stores: int
    paid_stores: int
    trial_stores: int
    inactive_stores: int
    monthly_cost: float
    addon_monthly_cost: float
    attention_count: int


# What a store needs the owner to DO, worst-first. Empty string means
# nothing to do. Kept as plain slugs so the SPA owns the wording and
# the pill tone (UI-STANDARDS section 3).
_ATTENTION_ORDER = (
    "retention",     # subscription cancelled, data on a purge clock
    "trial_expired",
    "inactive",
    "trial_ending",
    "",
)


def _attention_for(
    plan: str, trial_status: str, trial_days_left: int | None,
    retention_days_left: int | None,
) -> str:
    """Classify what (if anything) this store needs from the owner.

    Retention outranks everything: a store past cancellation is on a
    countdown to permanent deletion, which is the only irreversible
    state in the list.
    """
    if retention_days_left is not None:
        return "retention"
    if plan == "inactive":
        return "inactive"
    if trial_status == "expired":
        return "trial_expired"
    if trial_status in ("expiring_soon", "grace"):
        return "trial_ending"
    if plan == "trial" and trial_days_left is not None and trial_days_left <= 3:
        return "trial_ending"
    return ""


def owner_billing_rollup(
    db: Session, store_ids: list[int],
) -> tuple[list[OwnerBillingStore], OwnerBillingTotals]:
    """Per-store billing state + umbrella totals.

    Returns ``([], zeroed totals)`` for an owner with no linked
    stores — an empty umbrella is a legitimate state (a brand-new
    owner account), not an error.
    """
    from api.Modules.Billing.Services import (
        ADDONS_CATALOG, data_retention_days_left, get_trial_status,
        plan_label, plan_monthly_cents, plan_price_label,
        store_addon_keys, store_has_paid_plan,
    )
    from api.Modules.Tenancy.Models import Store

    totals: OwnerBillingTotals = {
        "stores": 0, "paid_stores": 0, "trial_stores": 0,
        "inactive_stores": 0, "monthly_cost": 0.0,
        "addon_monthly_cost": 0.0, "attention_count": 0,
    }
    if not store_ids:
        return [], totals

    stores = (
        db.query(Store)
        .filter(Store.id.in_(store_ids))
        .order_by(Store.name.asc())
        .all()
    )

    now = utc_now()
    rows: list[OwnerBillingStore] = []
    for store in stores:
        plan = store.plan or ""
        cycle = store.billing_cycle or ""

        trial_status = get_trial_status(store)
        trial_days_left: int | None = None
        if plan == "trial" and store.trial_ends_at is not None:
            trial_days_left = max(0, (store.trial_ends_at - now).days)

        # Add-ons are billed monthly regardless of the plan's cadence.
        addon_keys = [
            k for k in store_addon_keys(store) if k in ADDONS_CATALOG
        ]
        addon_cents = sum(
            int(ADDONS_CATALOG[k].get("price_cents", 0)) for k in addon_keys
        )
        plan_cents = plan_monthly_cents(plan, cycle)
        retention_left = data_retention_days_left(store)

        rows.append(OwnerBillingStore(
            store_id=store.id,
            store_name=store.name or "",
            store_slug=store.slug or "",
            plan=plan,
            plan_label=plan_label(plan, cycle),
            plan_price_label=plan_price_label(plan, cycle),
            billing_cycle=cycle,
            monthly_cost=round(plan_cents / 100, 2),
            trial_status=trial_status,
            trial_days_left=trial_days_left,
            trial_ends_at=(
                store.trial_ends_at.isoformat()
                if store.trial_ends_at else None
            ),
            retention_days_left=retention_left,
            addon_count=len(addon_keys),
            addon_monthly_cost=round(addon_cents / 100, 2),
            has_paid_plan=store_has_paid_plan(store),
            attention=_attention_for(
                plan, trial_status, trial_days_left, retention_left,
            ),
        ))

        totals["stores"] += 1
        totals["monthly_cost"] += plan_cents / 100
        totals["addon_monthly_cost"] += addon_cents / 100
        if store_has_paid_plan(store):
            totals["paid_stores"] += 1
        elif plan == "trial":
            totals["trial_stores"] += 1
        elif plan == "inactive":
            totals["inactive_stores"] += 1

    # Needs-attention stores float to the top; the rest keep their
    # alphabetical order so the list is stable between loads.
    rows.sort(key=lambda r: (
        _ATTENTION_ORDER.index(r["attention"]),
        r["store_name"].lower(),
    ))

    totals["attention_count"] = sum(1 for r in rows if r["attention"])
    totals["monthly_cost"] = round(totals["monthly_cost"], 2)
    totals["addon_monthly_cost"] = round(totals["addon_monthly_cost"], 2)
    return rows, totals


def owner_billing_payload(db: Session, user: Any) -> dict[str, Any]:
    """Controller-shaped payload for ``GET /owner/billing``."""
    from api.Modules.Owners.Services.dashboard import owner_store_ids

    rows, totals = owner_billing_rollup(db, owner_store_ids(db, user))
    return {"rows": rows, "totals": totals}
