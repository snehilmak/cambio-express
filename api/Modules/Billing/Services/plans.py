"""Plan catalog — the single source of truth for what each plan is
called and what it costs.

Before this module the same numbers lived in three places that had
already drifted apart: the admin subscription route carried
``{"basic": "$35 / month", "pro": "$45 / month"}``, the superadmin
MRR calculator carried its own ``_PRO_YEARLY_PRICE = 420``, and the
SPA pricing tiles said Pro-yearly costs **$450**.  $450 is the price
we actually sell (Pro is $45/mo and yearly is advertised as "two
months free": 45 x 12 - 90 = 450), so platform MRR was
under-reporting every Pro-yearly store by $2.50/month.  One catalog,
one set of numbers, no drift.

Prices are stored in **cents** — the same convention as the rest of
the money layer (Phase-0 float->cents migration) and as
``ADDONS_CATALOG``.  Formatting for humans is a display concern:
call :func:`plan_price_label`.

The dollar figures here are what the product *advertises* on the
pricing page.  The amount Stripe actually charges comes from the
Price IDs in :mod:`api.Modules.Billing.Services.checkout`; if the two
ever disagree, Stripe wins for the customer's card and this catalog
is what needs correcting.  Keep them in sync when prices change.
"""
from typing import TypedDict


class PlanSpec(TypedDict):
    label: str
    # Advertised price for one billing period, in cents. 0 for plans
    # that are never charged (trial / inactive).
    price_cents: int
    # What the customer is billed on: "monthly", "yearly", or "" for
    # the non-billable states.
    cycle: str


# Keyed by the checkout plan key. `basic` / `pro` are also the values
# `Store.plan` takes; the `_yearly` variants are billing-cadence
# copies that map back to the same `Store.plan` with
# `Store.billing_cycle = "yearly"`.
PLAN_CATALOG: dict[str, PlanSpec] = {
    "trial": {
        "label": "Free Trial", "price_cents": 0, "cycle": "",
    },
    "inactive": {
        "label": "Inactive", "price_cents": 0, "cycle": "",
    },
    "basic": {
        "label": "Basic", "price_cents": 3_500, "cycle": "monthly",
    },
    "basic_yearly": {
        # $35/mo advertised as "two months free" yearly.
        "label": "Basic (yearly)", "price_cents": 35_000, "cycle": "yearly",
    },
    "pro": {
        "label": "Pro", "price_cents": 4_500, "cycle": "monthly",
    },
    "pro_yearly": {
        "label": "Pro (yearly)", "price_cents": 45_000, "cycle": "yearly",
    },
}

# Plans a store can actually be billed for, in display order.
PAID_PLAN_KEYS = ("basic", "basic_yearly", "pro", "pro_yearly")


def plan_key(plan: str | None, billing_cycle: str | None = None) -> str:
    """Resolve a ``(Store.plan, Store.billing_cycle)`` pair to a
    catalog key.

    ``Store.plan`` stores the base name (``"pro"``) and the cadence
    lives separately in ``Store.billing_cycle``, so a yearly Pro
    store is ``("pro", "yearly")`` -> ``"pro_yearly"``.
    """
    base = (plan or "").strip()
    if not base:
        return ""
    if billing_cycle == "yearly":
        yearly = f"{base}_yearly"
        if yearly in PLAN_CATALOG:
            return yearly
    return base if base in PLAN_CATALOG else ""


def plan_label(plan: str | None, billing_cycle: str | None = None) -> str:
    """Human-readable plan name. ``"Unknown"`` for anything the
    catalog doesn't recognise — matching the previous behaviour of
    the admin subscription route."""
    spec = PLAN_CATALOG.get(plan_key(plan, billing_cycle))
    return spec["label"] if spec else "Unknown"


def plan_price_cents(
    plan: str | None, billing_cycle: str | None = None,
) -> int:
    """Advertised price for one billing period, in cents. 0 for
    trial / inactive / unrecognised plans."""
    spec = PLAN_CATALOG.get(plan_key(plan, billing_cycle))
    return spec["price_cents"] if spec else 0


def plan_monthly_cents(
    plan: str | None, billing_cycle: str | None = None,
) -> int:
    """Price normalised to a month, in cents — yearly plans are
    amortised /12 so plans on different cadences can be summed into
    one recurring figure (MRR, an owner's combined monthly spend).

    Rounded to the nearest cent; a $350/yr Basic is $29.17/mo.
    """
    spec = PLAN_CATALOG.get(plan_key(plan, billing_cycle))
    if not spec:
        return 0
    if spec["cycle"] == "yearly":
        return round(spec["price_cents"] / 12)
    return spec["price_cents"]


def plan_price_label(
    plan: str | None, billing_cycle: str | None = None,
) -> str:
    """Price rendered the way the subscription page shows it —
    ``"$35 / month"``, ``"$350 / year"``. Empty string for plans
    with nothing to charge, so callers can render a blank cell."""
    key = plan_key(plan, billing_cycle)
    spec = PLAN_CATALOG.get(key)
    if not spec or not spec["price_cents"]:
        return ""
    dollars = spec["price_cents"] / 100
    amount = (
        f"${dollars:,.0f}" if dollars == int(dollars) else f"${dollars:,.2f}"
    )
    period = "year" if spec["cycle"] == "yearly" else "month"
    return f"{amount} / {period}"
