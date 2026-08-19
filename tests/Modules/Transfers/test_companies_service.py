"""Unit tests for Transfers.Services.companies (PR 80)."""
from unittest.mock import MagicMock


def _store(companies=None, disabled=""):
    s = MagicMock()
    s.companies = companies
    s.companies_disabled = disabled
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



# ── disabled toggles (store_mt_company_roster) ────────────


def test_roster_marks_disabled_companies():
    from api.Modules.Transfers.Services import store_mt_company_roster
    roster = store_mt_company_roster(
        _store("Intermex,Maxi,Barri", disabled="Maxi"),
    )
    assert roster == [
        ("Intermex", True), ("Maxi", False), ("Barri", True),
    ]


def test_active_list_excludes_disabled():
    """The daily book / transfer form consume only enabled names."""
    from api.Modules.Transfers.Services import store_mt_companies
    result = store_mt_companies(_store("Intermex,Maxi,Barri", disabled="Maxi"))
    assert result == ["Intermex", "Barri"]


def test_disabled_match_is_case_insensitive():
    from api.Modules.Transfers.Services import store_mt_companies
    result = store_mt_companies(_store("Intermex,Maxi", disabled="maxi"))
    assert result == ["Intermex"]


def test_all_disabled_returns_empty_not_defaults():
    """A configured roster with everything toggled off must NOT
    fall back to the defaults — the operator chose 'nothing'."""
    from api.Modules.Transfers.Services import store_mt_companies
    result = store_mt_companies(
        _store("Intermex,Maxi", disabled="Intermex,Maxi"),
    )
    assert result == []


def test_default_roster_respects_disabled():
    """Unconfigured roster (defaults) still honors a disabled
    entry — defensive; the write path always sets both columns."""
    from api.Modules.Transfers.Services import store_mt_companies
    result = store_mt_companies(_store("", disabled="Barri"))
    assert result == ["Intermex", "Maxi"]


# ── encode_mt_companies (Settings write path) ─────────────


def _entries(*pairs):
    return [{"name": n, "enabled": e} for n, e in pairs]


def test_encode_roundtrip():
    from api.Modules.Transfers.Services import encode_mt_companies
    companies, disabled = encode_mt_companies(
        _entries(("Intermex", True), ("Maxi", False), ("Ria", True)),
    )
    assert companies == "Intermex,Maxi,Ria"
    assert disabled == "Maxi"


def test_encode_strips_whitespace():
    from api.Modules.Transfers.Services import encode_mt_companies
    companies, disabled = encode_mt_companies(
        _entries(("  Intermex  ", True)),
    )
    assert companies == "Intermex"
    assert disabled == ""


def test_encode_rejects_empty_name():
    import pytest
    from api.Modules.Transfers.Services import encode_mt_companies
    with pytest.raises(ValueError):
        encode_mt_companies(_entries(("   ", True)))


def test_encode_rejects_comma_in_name():
    import pytest
    from api.Modules.Transfers.Services import encode_mt_companies
    with pytest.raises(ValueError):
        encode_mt_companies(_entries(("Ria, Inc", True)))


def test_encode_rejects_case_insensitive_duplicate():
    import pytest
    from api.Modules.Transfers.Services import encode_mt_companies
    with pytest.raises(ValueError):
        encode_mt_companies(_entries(("Maxi", True), ("maxi", False)))


def test_encode_rejects_overlong_name():
    import pytest
    from api.Modules.Transfers.Services import (
        MAX_MT_COMPANY_NAME_LEN, encode_mt_companies,
    )
    with pytest.raises(ValueError):
        encode_mt_companies(
            _entries(("X" * (MAX_MT_COMPANY_NAME_LEN + 1), True)),
        )


def test_encode_rejects_empty_roster():
    import pytest
    from api.Modules.Transfers.Services import encode_mt_companies
    with pytest.raises(ValueError):
        encode_mt_companies([])


def test_encode_rejects_over_cap():
    import pytest
    from api.Modules.Transfers.Services import (
        MAX_MT_COMPANIES, encode_mt_companies,
    )
    with pytest.raises(ValueError):
        encode_mt_companies(
            _entries(*[(f"Co{i}", True) for i in range(MAX_MT_COMPANIES + 1)]),
        )


def test_encode_allows_all_disabled():
    """All-off is a legitimate operator choice — UIs show their
    empty states rather than the write being rejected."""
    from api.Modules.Transfers.Services import encode_mt_companies
    companies, disabled = encode_mt_companies(
        _entries(("Intermex", False), ("Maxi", False)),
    )
    assert companies == "Intermex,Maxi"
    assert disabled == "Intermex,Maxi"
