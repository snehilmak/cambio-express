"""Unit tests for Transfers.Services.tax (PR 76)."""
from unittest.mock import MagicMock


def _store(rate=0.01):
    s = MagicMock()
    s.federal_tax_rate = rate
    return s


# ── normalize_service_type ────────────────────────────────


def test_normalize_known_service_passes_through():
    from api.Modules.Transfers.Services import normalize_service_type
    assert normalize_service_type("Money Transfer") == "Money Transfer"
    assert normalize_service_type("Bill Payment") == "Bill Payment"
    assert normalize_service_type("Top Up") == "Top Up"
    assert normalize_service_type("Recharge") == "Recharge"


def test_normalize_unknown_falls_back_to_money_transfer():
    """Bad client value can't quietly disable tax — fall back
    to the historical default."""
    from api.Modules.Transfers.Services import normalize_service_type
    assert normalize_service_type("garbage") == "Money Transfer"
    assert normalize_service_type("") == "Money Transfer"
    assert normalize_service_type(None) == "Money Transfer"


def test_normalize_strips_whitespace():
    from api.Modules.Transfers.Services import normalize_service_type
    assert normalize_service_type("  Bill Payment  ") == "Bill Payment"


# ── federal_tax_for ───────────────────────────────────────


def test_money_transfer_to_foreign_country_taxed():
    """Standard remittance — full tax applied."""
    from api.Modules.Transfers.Services import federal_tax_for
    s = _store(rate=0.01)
    # $1000 * 1% = $10.00
    assert federal_tax_for(
        1000.0, "Money Transfer", s, country="Mexico",
    ) == 10.0


def test_money_transfer_domestic_zero_tax():
    """US-to-US money transfer skips the tax — IRS only collects
    on money leaving the country."""
    from api.Modules.Transfers.Services import federal_tax_for
    s = _store(rate=0.01)
    assert federal_tax_for(
        1000.0, "Money Transfer", s, country="United States",
    ) == 0.0


def test_bill_payment_zero_tax_regardless_of_country():
    from api.Modules.Transfers.Services import federal_tax_for
    s = _store(rate=0.01)
    # Foreign country, but Bill Payment is exempt.
    assert federal_tax_for(
        1000.0, "Bill Payment", s, country="Mexico",
    ) == 0.0


def test_top_up_zero_tax():
    from api.Modules.Transfers.Services import federal_tax_for
    s = _store(rate=0.01)
    assert federal_tax_for(
        500.0, "Top Up", s, country="Mexico",
    ) == 0.0


def test_recharge_zero_tax():
    from api.Modules.Transfers.Services import federal_tax_for
    s = _store(rate=0.01)
    assert federal_tax_for(
        500.0, "Recharge", s, country="Mexico",
    ) == 0.0


def test_zero_amount_returns_zero_tax():
    from api.Modules.Transfers.Services import federal_tax_for
    s = _store(rate=0.01)
    assert federal_tax_for(
        0.0, "Money Transfer", s, country="Mexico",
    ) == 0.0
    assert federal_tax_for(
        None, "Money Transfer", s, country="Mexico",
    ) == 0.0


def test_no_store_returns_zero_tax():
    """Defensive: if store somehow isn't passed, tax is 0."""
    from api.Modules.Transfers.Services import federal_tax_for
    assert federal_tax_for(
        1000.0, "Money Transfer", None, country="Mexico",
    ) == 0.0


def test_zero_rate_returns_zero_tax():
    """A store with rate=0 (or unset) doesn't tax."""
    from api.Modules.Transfers.Services import federal_tax_for
    s = _store(rate=0)
    assert federal_tax_for(
        1000.0, "Money Transfer", s, country="Mexico",
    ) == 0.0


def test_tax_rounded_to_cents():
    """Round half-up to two decimals — operators can't reconcile
    fractional cents on a daily book."""
    from api.Modules.Transfers.Services import federal_tax_for
    # 0.015 rate * $123.45 = $1.85175 → rounds to $1.85
    s = _store(rate=0.015)
    assert federal_tax_for(
        123.45, "Money Transfer", s, country="Mexico",
    ) == 1.85


def test_country_with_whitespace_still_matches_domestic():
    """Form input may leave whitespace around 'United States';
    `.strip()` makes the domestic check resilient."""
    from api.Modules.Transfers.Services import federal_tax_for
    s = _store(rate=0.01)
    assert federal_tax_for(
        1000.0, "Money Transfer", s, country="  United States  ",
    ) == 0.0


def test_no_country_taxed_when_money_transfer():
    """When country is None (legacy form submissions), the
    domestic check is skipped — Money Transfer tax applies."""
    from api.Modules.Transfers.Services import federal_tax_for
    s = _store(rate=0.01)
    assert federal_tax_for(
        1000.0, "Money Transfer", s, country=None,
    ) == 10.0


# ── constants ─────────────────────────────────────────────


def test_service_types_includes_canonical_four():
    from api.Modules.Transfers.Services import SERVICE_TYPES
    assert SERVICE_TYPES == (
        "Money Transfer", "Bill Payment", "Top Up", "Recharge",
    )


def test_tax_exempt_excludes_money_transfer():
    """Only Money Transfer carries tax."""
    from api.Modules.Transfers.Services import TAX_EXEMPT_SERVICES
    assert "Money Transfer" not in TAX_EXEMPT_SERVICES
    assert "Bill Payment" in TAX_EXEMPT_SERVICES
    assert "Top Up" in TAX_EXEMPT_SERVICES
    assert "Recharge" in TAX_EXEMPT_SERVICES


def test_domestic_countries_includes_united_states():
    from api.Modules.Transfers.Services import DOMESTIC_COUNTRIES
    assert "United States" in DOMESTIC_COUNTRIES


def test_transfer_countries_includes_us_and_other():
    from api.Modules.Transfers.Services import TRANSFER_COUNTRIES
    assert "United States" in TRANSFER_COUNTRIES
    assert "Other" in TRANSFER_COUNTRIES


# ── legacy Flask wrappers ─────────────────────────────────






