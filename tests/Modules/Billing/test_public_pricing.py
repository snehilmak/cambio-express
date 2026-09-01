"""Marketing prices come from PLAN_CATALOG (W-1).

The landing page kept its own copy of the prices and it drifted: it
advertised Pro yearly at $420 while checkout charged $450. That is
not a cosmetic bug — it is a public page quoting a price we do not
honour.

PLAN_CATALOG itself exists because prices had already been
duplicated into three modules and two went stale (CLAUDE.md, "Reuse
before you build"). The marketing page was quietly the fourth copy.
These tests keep it the last one.
"""
import pytest

from api.Modules.Billing.Services.plans import PLAN_CATALOG, public_pricing


def test_pricing_matches_the_catalog_exactly():
    """The assertion that would have caught the $420/$450 gap."""
    by_key = {p["key"]: p for p in public_pricing()}
    for base in ("basic", "pro"):
        assert by_key[base]["monthly_cents"] == (
            PLAN_CATALOG[base]["price_cents"]
        )
        assert by_key[base]["yearly_cents"] == (
            PLAN_CATALOG[f"{base}_yearly"]["price_cents"]
        )


def test_pro_yearly_is_450_not_420():
    """Pinned explicitly because this is the number that was wrong
    on the live page."""
    pro = next(p for p in public_pricing() if p["key"] == "pro")
    assert pro["yearly_cents"] == 45_000
    assert pro["yearly_cents"] != 42_000


def test_months_free_is_derived_not_asserted():
    """The page says "N months free". That claim has to follow from
    the two prices, not from a hand-typed number that can outlive a
    price change."""
    for plan in public_pricing():
        monthly = plan["monthly_cents"]
        yearly = plan["yearly_cents"]
        saved = (monthly * 12) - yearly
        assert plan["months_free"] == saved // monthly


def test_months_free_never_rounds_in_our_favour():
    """A claim that rounds up is the kind that ends in a complaint."""
    for plan in public_pricing():
        implied = plan["monthly_cents"] * (12 - plan["months_free"])
        assert implied >= plan["yearly_cents"], (
            f"{plan['key']} claims more free months than the price gives"
        )


def test_the_endpoint_needs_no_login(client):
    """It renders before anyone has an account."""
    resp = client.get("/api/v2/billing/pricing")
    assert resp.status_code == 200, resp.text
    keys = {p["key"] for p in resp.json()["plans"]}
    assert keys == {"basic", "pro"}
