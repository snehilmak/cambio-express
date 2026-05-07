"""Unit tests for Transfers.Services.companies (PR 80)."""
from unittest.mock import MagicMock


def _store(companies=None):
    s = MagicMock()
    s.companies = companies
    return s


# ── DEFAULT_MT_COMPANIES ──────────────────────────────────


def test_default_includes_canonical_three():
    """The historical default is Intermex / Maxi / Barri —
    losing one breaks signup."""
    from api.Modules.Transfers.Services import DEFAULT_MT_COMPANIES
    assert "Intermex" in DEFAULT_MT_COMPANIES
    assert "Maxi" in DEFAULT_MT_COMPANIES
    assert "Barri" in DEFAULT_MT_COMPANIES


# ── store_mt_companies ────────────────────────────────────


def test_returns_default_when_store_is_none():
    """Defensive: superadmin views may pass None."""
    from api.Modules.Transfers.Services import (
        DEFAULT_MT_COMPANIES, store_mt_companies,
    )
    result = store_mt_companies(None)
    assert result == DEFAULT_MT_COMPANIES


def test_returns_default_when_companies_blank():
    from api.Modules.Transfers.Services import (
        DEFAULT_MT_COMPANIES, store_mt_companies,
    )
    assert store_mt_companies(_store("")) == DEFAULT_MT_COMPANIES
    assert store_mt_companies(_store(None)) == DEFAULT_MT_COMPANIES
    # Whitespace-only also blank.
    assert store_mt_companies(_store("   ")) == DEFAULT_MT_COMPANIES


def test_returns_csv_list_when_companies_set():
    """Custom set on the Store row → use it instead of default."""
    from api.Modules.Transfers.Services import store_mt_companies
    result = store_mt_companies(_store("Ria,Western Union,Sigue"))
    assert result == ["Ria", "Western Union", "Sigue"]


def test_strips_whitespace_from_csv_entries():
    from api.Modules.Transfers.Services import store_mt_companies
    result = store_mt_companies(
        _store("  Intermex  ,  Maxi  ,  Barri  "),
    )
    assert result == ["Intermex", "Maxi", "Barri"]


def test_drops_empty_csv_entries():
    """Trailing commas or double commas don't produce empty
    strings in the result."""
    from api.Modules.Transfers.Services import store_mt_companies
    result = store_mt_companies(_store("Intermex,,Maxi,"))
    assert result == ["Intermex", "Maxi"]


def test_returns_fresh_list_caller_can_mutate():
    """Mutating the returned list must NOT affect the default
    or any subsequent call."""
    from api.Modules.Transfers.Services import (
        DEFAULT_MT_COMPANIES, store_mt_companies,
    )
    result = store_mt_companies(None)
    result.append("CustomCompany")
    # Default unchanged.
    assert "CustomCompany" not in DEFAULT_MT_COMPANIES
    # Next call returns a fresh default copy.
    fresh = store_mt_companies(None)
    assert "CustomCompany" not in fresh


def test_preserves_company_order_from_csv():
    """Operators care about the dropdown order — preserve the
    CSV order rather than alphabetize."""
    from api.Modules.Transfers.Services import store_mt_companies
    result = store_mt_companies(
        _store("Zelle,Apple Pay,Cash App"),
    )
    assert result == ["Zelle", "Apple Pay", "Cash App"]


# ── legacy Flask wrappers ─────────────────────────────────


def test_legacy_default_re_exported():
    from app import DEFAULT_MT_COMPANIES as legacy
    from api.Modules.Transfers.Services import (
        DEFAULT_MT_COMPANIES as service,
    )
    assert legacy is service


def test_legacy_store_mt_companies_delegates():
    from app import store_mt_companies as legacy
    result = legacy(_store("Intermex,Maxi"))
    assert result == ["Intermex", "Maxi"]
    # Default fallback works through the legacy wrapper too.
    from api.Modules.Transfers.Services import DEFAULT_MT_COMPANIES
    assert legacy(None) == DEFAULT_MT_COMPANIES
