"""TV-display country picker — Phase 3 of the logo rollout.

Tests for the curated dropdown that replaces the free-text country
fields on the admin landing's Add-Country form and the country
editor's section header.
"""
from app import (
    db, Store, TVDisplay, TVDisplayCountry,
    _TV_COUNTRY_PICKER,
)


def _activate_addon(client, store_id):
    with client.application.app_context():
        s = db.session.get(Store, store_id)
        s.plan   = "basic"
        s.addons = "tv_display"
        db.session.commit()


# ── Picker list itself ─────────────────────────────────────────

def test_picker_list_starts_with_us_latam_corridor():
    """Heaviest senders first — operators pick from the top of the
    list ~80% of the time. Order is intentional."""
    iso_codes = [iso for iso, _ in _TV_COUNTRY_PICKER]
    # Top of the list is the US→LATAM corridor.
    assert iso_codes[:5] == ["MX", "GT", "HN", "SV", "DO"]


def test_picker_list_uses_uppercase_iso2():
    """Sloppy lowercase codes break the flag-emoji helper."""
    for iso, _ in _TV_COUNTRY_PICKER:
        assert len(iso) == 2
        assert iso == iso.upper()


def test_picker_list_has_no_duplicates():
    """No two entries share an ISO-2 code or a display name —
    otherwise the picker shows duplicates."""
    iso_codes = [iso for iso, _ in _TV_COUNTRY_PICKER]
    names     = [name for _, name in _TV_COUNTRY_PICKER]
    assert len(iso_codes) == len(set(iso_codes))
    assert len(names)     == len(set(names))


# ── Admin landing's Add-Country form ───────────────────────────

def test_admin_landing_renders_country_picker(logged_in_client, test_store_id):
    _activate_addon(logged_in_client, test_store_id)
    body = logged_in_client.get("/tv-display").data.decode()
    # Picker dropdown is present with curated entries.
    assert 'id="tvc-add-country-code"' in body
    assert 'value="MX"' in body
    assert 'data-name="Mexico"' in body
    assert 'data-name="Guatemala"' in body
    # Choices.js wrapper class is on the underlying <select>; the
    # flag-icons SVG is rendered into each option client-side from
    # the option's value (ISO-2 code) by tv-country-picker.js.
    assert 'js-country-picker' in body
    # Display names are present somewhere in the form region.
    assert "Mexico" in body
    assert "Guatemala" in body


def test_admin_landing_picker_no_longer_has_freetext_country_name(
        logged_in_client, test_store_id):
    """The two free-text inputs (country_name + country_code) on
    the Add-Country form have been replaced by the picker. Hidden
    name input is JS-synced, so name='country_name' on a <input
    type="text"> shouldn't appear on this form."""
    _activate_addon(logged_in_client, test_store_id)
    body = logged_in_client.get("/tv-display").data.decode()
    # The legacy text input is gone — verify by looking for its
    # placeholder which only existed on the old free-text input.
    assert 'placeholder="Mexico"' not in body
    # And the hidden country_name companion input IS present.
    assert 'id="tvc-add-country-name"' in body


def test_admin_landing_picker_submits_both_fields(logged_in_client, test_store_id):
    """Form contract preserved — the server still receives both
    country_code (from the select) AND country_name (from the
    hidden input). A real browser fills the hidden via JS; we
    simulate by POSTing both directly."""
    _activate_addon(logged_in_client, test_store_id)
    logged_in_client.get("/tv-display")
    resp = logged_in_client.post("/tv-display/countries/new", data={
        "country_code": "MX",
        "country_name": "Mexico",
    })
    assert resp.status_code == 302
    with logged_in_client.application.app_context():
        c = TVDisplayCountry.query.filter_by(country_code="MX").first()
        assert c is not None
        assert c.country_name == "Mexico"


# ── Country editor's section header ────────────────────────────

def test_editor_header_renders_picker_with_current_selected(
        logged_in_client, test_store_id):
    """Editing an MX country: the picker is pre-selected on the
    Mexico entry and the big topbar flag renders the MX SVG."""
    _activate_addon(logged_in_client, test_store_id)
    logged_in_client.get("/tv-display")
    logged_in_client.post("/tv-display/countries/new", data={
        "country_code": "MX", "country_name": "Mexico",
    })
    with logged_in_client.application.app_context():
        country_id = TVDisplayCountry.query.first().id
    body = logged_in_client.get(f"/tv-display/countries/{country_id}").data.decode()
    assert 'id="ce-country-picker"' in body
    assert 'js-country-picker' in body
    # MX option is present and selected.
    assert 'value="MX" data-name="Mexico"' in body
    assert 'selected' in body
    # Big topbar flag rendered as flag-icons SVG (mx in the class).
    assert 'class="fi fi-mx"' in body


def test_editor_header_preserves_legacy_freetext_country(
        logged_in_client, test_store_id):
    """A country saved with an ISO-2 NOT in the curated picker
    (e.g. legacy data) renders as '(custom) <name>' so the
    operator's data isn't silently lost."""
    _activate_addon(logged_in_client, test_store_id)
    logged_in_client.get("/tv-display")
    logged_in_client.post("/tv-display/countries/new", data={
        "country_code": "ZZ",  # not in the picker
        "country_name": "Atlantis",
    })
    with logged_in_client.application.app_context():
        country_id = TVDisplayCountry.query.first().id
    body = logged_in_client.get(f"/tv-display/countries/{country_id}").data.decode()
    assert "(custom) Atlantis" in body


def test_editor_header_preserves_legacy_no_iso_country(
        logged_in_client, test_store_id):
    """Pre-picker era: countries could be saved with country_name
    but no country_code at all. Render as a pre-selected custom
    option so the section is still editable without losing data."""
    _activate_addon(logged_in_client, test_store_id)
    logged_in_client.get("/tv-display")
    logged_in_client.post("/tv-display/countries/new", data={
        "country_name": "Sealand",  # no country_code
    })
    with logged_in_client.application.app_context():
        country_id = TVDisplayCountry.query.first().id
    body = logged_in_client.get(f"/tv-display/countries/{country_id}").data.decode()
    assert "(custom) Sealand" in body


# ── Save flow on the country editor ────────────────────────────

def test_editor_picker_submission_persists_country_change(
        logged_in_client, test_store_id):
    """Operator opens an MX country, picks Guatemala from the
    dropdown, hits Save → the country row updates. Server receives
    country_code=GT + country_name=Guatemala from the form, same
    contract as the free-text era."""
    _activate_addon(logged_in_client, test_store_id)
    logged_in_client.get("/tv-display")
    logged_in_client.post("/tv-display/countries/new", data={
        "country_code": "MX", "country_name": "Mexico",
    })
    with logged_in_client.application.app_context():
        country_id = TVDisplayCountry.query.first().id
    # Simulate the picker change + submit (browser would have
    # synced the hidden country_name from data-name; we mirror).
    resp = logged_in_client.post(f"/tv-display/countries/{country_id}", data={
        "country_code": "GT",
        "country_name": "Guatemala",
        "mt_companies": "",
    })
    assert resp.status_code == 302
    with logged_in_client.application.app_context():
        c = TVDisplayCountry.query.filter_by(id=country_id).first()
        assert c.country_code == "GT"
        assert c.country_name == "Guatemala"


# ── Public board renders the new country correctly ─────────────

def test_public_board_renders_picker_country_with_flag(
        client, logged_in_client, test_store_id):
    """End-to-end: pick Mexico from the dropdown → public board
    shows 🇲🇽 + 'Mexico' as the section header."""
    _activate_addon(logged_in_client, test_store_id)
    logged_in_client.get("/tv-display")
    logged_in_client.post("/tv-display/countries/new", data={
        "country_code": "MX", "country_name": "Mexico",
    })
    with logged_in_client.application.app_context():
        token = TVDisplay.query.first().public_token
    body = client.get(f"/tv/{token}").data.decode()
    # SVG flag (flag-icons) on the public board.
    assert 'class="fi fi-mx"' in body
    assert "Mexico" in body
