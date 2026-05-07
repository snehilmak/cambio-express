"""Unit tests for Customers.Services.phone_codes (PR 79)."""


def test_phone_country_codes_is_non_empty_list():
    from api.Modules.Customers.Services import PHONE_COUNTRY_CODES
    assert isinstance(PHONE_COUNTRY_CODES, list)
    assert len(PHONE_COUNTRY_CODES) > 0


def test_phone_country_codes_entries_are_pairs_of_strings():
    """Every entry must be a (dial_code, label) tuple of strings —
    the template iterates these directly into the dropdown."""
    from api.Modules.Customers.Services import PHONE_COUNTRY_CODES
    for entry in PHONE_COUNTRY_CODES:
        assert isinstance(entry, tuple)
        assert len(entry) == 2
        dial, label = entry
        assert isinstance(dial, str)
        assert isinstance(label, str)
        assert dial.startswith("+")
        assert label  # non-empty label


def test_phone_country_codes_starts_with_us():
    """US/Canada is the most common pick for US-based remittance
    storefronts — keep it at the top."""
    from api.Modules.Customers.Services import PHONE_COUNTRY_CODES
    first_dial, first_label = PHONE_COUNTRY_CODES[0]
    assert first_dial == "+1"
    assert "United States" in first_label


def test_phone_country_codes_includes_core_latam():
    """The core LATAM remittance corridors must always be
    present — losing one silently breaks the dropdown for that
    customer base."""
    from api.Modules.Customers.Services import PHONE_COUNTRY_CODES
    dials = {dial for dial, _ in PHONE_COUNTRY_CODES}
    expected_latam = {"+52", "+502", "+503", "+504", "+505",
                       "+506", "+507", "+57", "+593", "+51"}
    assert expected_latam.issubset(dials)


def test_phone_country_codes_no_duplicate_dial_codes():
    """Each dial code appears once — the dropdown shouldn't show
    duplicates."""
    from api.Modules.Customers.Services import PHONE_COUNTRY_CODES
    dials = [dial for dial, _ in PHONE_COUNTRY_CODES]
    assert len(dials) == len(set(dials))


# ── legacy Flask wrapper ──────────────────────────────────


def test_legacy_phone_country_codes_re_exported():
    """app.PHONE_COUNTRY_CODES is the same list object as the
    Service's — re-exported, not copied."""
    from app import PHONE_COUNTRY_CODES as legacy
    from api.Modules.Customers.Services import (
        PHONE_COUNTRY_CODES as service,
    )
    assert legacy is service
