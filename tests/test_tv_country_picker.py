"""TV-display country picker — picker list invariants + the
country editor + public-board paths.

The admin landing's Add-Country form moved to React in C-5a, so the
three legacy "renders the picker dropdown HTML" tests are gone — the
SPA picker is its own component and isn't HTML-asserted here. The
country editor (still on Flask) and the public kiosk page (still on
Flask) keep their tests; their setup uses the new JSON country-create
endpoint.
"""
from app import (
    db, Store, TVDisplay, TVDisplayCountry,
    _TV_COUNTRY_PICKER,
)
from tests._tv_display_helpers import create_country


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


# ── Country editor's section header ────────────────────────────







# ── Save flow on the country editor ────────────────────────────

def test_editor_picker_submission_persists_country_change(
        logged_in_client, test_store_id):
    """Operator opens an MX country, picks Guatemala from the
    dropdown, hits Save → the country row updates. Server receives
    country_code=GT + country_name=Guatemala from the form, same
    contract as the free-text era."""
    _activate_addon(logged_in_client, test_store_id)
    country_id = create_country(
        logged_in_client, test_store_id,
        country_name="Mexico", country_code="MX",
    )
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
    shows the MX flag SVG + 'Mexico' as the section header."""
    _activate_addon(logged_in_client, test_store_id)
    create_country(
        logged_in_client, test_store_id,
        country_name="Mexico", country_code="MX",
    )
    with logged_in_client.application.app_context():
        token = TVDisplay.query.first().public_token
    body = client.get(f"/tv/{token}").data.decode()
    # SVG flag (flag-icons) on the public board.
    assert 'class="fi fi-mx"' in body
    assert "Mexico" in body
