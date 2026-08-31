"""Plan catalog — the single source of truth for plan names and
prices. Pure functions, no DB."""
import pytest

from api.Modules.Billing.Services import (
    PAID_PLAN_KEYS, PLAN_CATALOG, plan_key, plan_label,
    plan_monthly_cents, plan_price_cents, plan_price_label,
)


def test_catalog_prices_match_what_the_pricing_page_sells():
    """These numbers are the product's advertised prices. Three
    modules used to keep private copies and two had drifted (a $420
    Pro-yearly in the MRR tile, a $49/$99 table in the SA reports);
    this test is the anchor that keeps them honest."""
    assert PLAN_CATALOG["basic"]["price_cents"] == 3_500
    assert PLAN_CATALOG["pro"]["price_cents"] == 4_500
    assert PLAN_CATALOG["basic_yearly"]["price_cents"] == 35_000
    assert PLAN_CATALOG["pro_yearly"]["price_cents"] == 45_000


def test_yearly_prices_are_the_advertised_two_months_free():
    """Yearly is sold as "two months free" — 10x the monthly price.
    A yearly figure that isn't 10x means one of the two drifted."""
    for base in ("basic", "pro"):
        monthly = PLAN_CATALOG[base]["price_cents"]
        yearly = PLAN_CATALOG[f"{base}_yearly"]["price_cents"]
        assert yearly == monthly * 10


def test_paid_plan_keys_are_all_billable():
    assert set(PAID_PLAN_KEYS) <= set(PLAN_CATALOG)
    for key in PAID_PLAN_KEYS:
        assert PLAN_CATALOG[key]["price_cents"] > 0
        assert PLAN_CATALOG[key]["cycle"] in ("monthly", "yearly")


# ── plan_key ─────────────────────────────────────────────────


@pytest.mark.parametrize("plan,cycle,expected", [
    ("basic", "monthly", "basic"),
    ("basic", "yearly", "basic_yearly"),
    ("pro", "yearly", "pro_yearly"),
    # Store.plan holds the base name and the cadence lives in
    # Store.billing_cycle; a missing cycle means monthly.
    ("pro", "", "pro"),
    ("pro", None, "pro"),
    ("trial", "", "trial"),
    # Trial/inactive have no yearly variant — don't invent one.
    ("trial", "yearly", "trial"),
    ("", "monthly", ""),
    (None, None, ""),
    ("nonsense", "monthly", ""),
])
def test_plan_key_resolves_plan_and_cycle(plan, cycle, expected):
    assert plan_key(plan, cycle) == expected


# ── labels + prices ──────────────────────────────────────────


def test_plan_label_distinguishes_cadence():
    assert plan_label("basic", "monthly") == "Basic"
    assert plan_label("basic", "yearly") == "Basic (yearly)"
    assert plan_label("trial", "") == "Free Trial"
    assert plan_label("inactive", "") == "Inactive"
    assert plan_label(None, None) == "Unknown"


def test_plan_price_label_shows_the_right_period():
    """A yearly store used to be shown "$35 / month" on its own
    subscription page because the label table was monthly-only."""
    assert plan_price_label("basic", "monthly") == "$35 / month"
    assert plan_price_label("pro", "monthly") == "$45 / month"
    assert plan_price_label("basic", "yearly") == "$350 / year"
    assert plan_price_label("pro", "yearly") == "$450 / year"
    # Nothing to charge → blank cell, not "$0".
    assert plan_price_label("trial", "") == ""
    assert plan_price_label("inactive", "") == ""
    assert plan_price_label("nonsense", "") == ""


def test_plan_price_cents_is_the_period_price():
    assert plan_price_cents("pro", "yearly") == 45_000
    assert plan_price_cents("pro", "monthly") == 4_500
    assert plan_price_cents("trial", "") == 0
    assert plan_price_cents("nonsense", "") == 0


def test_plan_monthly_cents_amortises_yearly_plans():
    """Yearly plans normalise to /12 so plans on different cadences
    can be summed into one recurring figure."""
    assert plan_monthly_cents("basic", "monthly") == 3_500
    assert plan_monthly_cents("basic", "yearly") == round(35_000 / 12)
    assert plan_monthly_cents("pro", "yearly") == round(45_000 / 12)
    # A yearly plan is always cheaper per month than the monthly one.
    assert plan_monthly_cents("pro", "yearly") < plan_monthly_cents(
        "pro", "monthly",
    )
    assert plan_monthly_cents("trial", "") == 0
