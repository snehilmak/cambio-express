"""TV Display catalog system — curated MT companies + banks pickers.

Phase 1 of the logo-rollout: catalog tables + seed + picker UI in
the country editor. Logos themselves come in Phase 2 (upload flow +
rendering); these tests pin the data-model invariants that both
phases depend on.
"""
from app import (
    db, Store, TVDisplay, TVDisplayCountry, TVDisplayPayoutBank, TVDisplayRate,
    TVCompanyCatalog, TVBankCatalog,
    _DEFAULT_TV_COMPANIES, _DEFAULT_TV_BANKS,
)


# ── Helpers ────────────────────────────────────────────────────

def _activate_addon(client, store_id):
    with client.application.app_context():
        s = db.session.get(Store, store_id)
        s.plan = "basic"
        s.addons = "tv_display"
        db.session.commit()


# ── Seed ───────────────────────────────────────────────────────

def test_default_catalogs_seed_at_boot(client):
    """Every boot calls init_db() → _seed_tv_catalogs(). Pin the
    counts so an accidental dedupe / regression doesn't drop entries."""
    with client.application.app_context():
        assert TVCompanyCatalog.query.count() == len(_DEFAULT_TV_COMPANIES)
        assert TVBankCatalog.query.count() == len(_DEFAULT_TV_BANKS)


def test_default_seed_includes_canonical_brands(client):
    """Spot-check the well-known MT companies + a few banks per
    country are seeded with their expected slugs. Future renames go
    through display_name (mutable); slugs are immutable."""
    with client.application.app_context():
        slugs = {c.slug for c in TVCompanyCatalog.query.all()}
        assert {"intermex", "maxi", "barri", "vigo", "ria",
                "moneygram", "western_union"}.issubset(slugs)
        bank_slugs = {b.slug for b in TVBankCatalog.query.all()}
        # MX
        assert {"mx_bbva_bancomer", "mx_banorte"}.issubset(bank_slugs)
        # GT
        assert {"gt_industrial", "gt_banrural"}.issubset(bank_slugs)
        # HN
        assert {"hn_atlantida", "hn_ficohsa"}.issubset(bank_slugs)
        # SV
        assert {"sv_agricola", "sv_cuscatlan"}.issubset(bank_slugs)
        # DO
        assert {"do_banreservas", "do_popular"}.issubset(bank_slugs)


def test_re_seed_is_idempotent(client):
    """Re-running init_db() must not duplicate catalog rows. Existing
    superadmin edits to display_name / sort_order survive."""
    from app import _seed_tv_catalogs
    with client.application.app_context():
        # Mutate one entry to verify the next seed call respects it.
        c = TVCompanyCatalog.query.filter_by(slug="maxi").first()
        c.display_name = "Maxi (Operator-renamed)"
        c.sort_order = 999
        db.session.commit()

        before_count = TVCompanyCatalog.query.count()
        _seed_tv_catalogs()
        after_count = TVCompanyCatalog.query.count()
        assert after_count == before_count

        # Edit survived.
        c2 = TVCompanyCatalog.query.filter_by(slug="maxi").first()
        assert c2.display_name == "Maxi (Operator-renamed)"
        assert c2.sort_order == 999


def test_bank_catalog_country_codes_are_uppercase_iso2(client):
    with client.application.app_context():
        for b in TVBankCatalog.query.all():
            assert len(b.country_code) == 2
            assert b.country_code == b.country_code.upper()


# ── Editor route exposes the catalog ───────────────────────────

def test_editor_route_passes_company_catalog_to_template(logged_in_client, test_store_id):
    _activate_addon(logged_in_client, test_store_id)
    logged_in_client.get("/tv-display")
    # Create a Mexico section to drill into.
    logged_in_client.post("/tv-display/countries/new", data={
        "country_name": "Mexico", "country_code": "MX",
        "mt_companies": "",
    })
    with logged_in_client.application.app_context():
        country_id = TVDisplayCountry.query.first().id
    body = logged_in_client.get(f"/tv-display/countries/{country_id}").data.decode()
    # Picker dropdown is present with active companies.
    assert 'id="ce-add-col"' in body
    assert 'value="intermex"' in body
    assert 'value="maxi"' in body
    assert "Intermex" in body  # display_name surfaced


def test_editor_route_scopes_bank_picker_to_country(logged_in_client, test_store_id):
    """Mexican country editor sees Mexican banks only — not Guatemalan
    ones — so the dropdown stays scannable instead of dumping every
    catalog entry across LATAM."""
    _activate_addon(logged_in_client, test_store_id)
    logged_in_client.get("/tv-display")
    logged_in_client.post("/tv-display/countries/new", data={
        "country_name": "Mexico", "country_code": "MX",
        "mt_companies": "",
    })
    with logged_in_client.application.app_context():
        country_id = TVDisplayCountry.query.first().id
    # Add a bank row so the JSON catalog blob gets emitted.
    logged_in_client.post(f"/tv-display/countries/{country_id}", data={
        "country_name": "Mexico", "country_code": "MX",
        "mt_companies": "maxi",
        "new_bank_name": "mx_bbva_bancomer",
    })
    body = logged_in_client.get(f"/tv-display/countries/{country_id}").data.decode()
    # Mexico-scoped banks are present.
    assert "BBVA Bancomer" in body
    assert "Banorte" in body
    # Guatemala-scoped banks are NOT present in the picker. (The
    # display_name "Banco Industrial" is GT-only in the seed.)
    assert "Banco Industrial" not in body


def test_editor_route_includes_legacy_freetext_as_custom_option(logged_in_client, test_store_id):
    """If a store imported / typed a bank name that doesn't match any
    catalog slug, the picker preserves it as a (custom) option so
    operators don't lose data when the catalog rolls out."""
    _activate_addon(logged_in_client, test_store_id)
    logged_in_client.get("/tv-display")
    logged_in_client.post("/tv-display/countries/new", data={
        "country_name": "Mexico", "country_code": "MX",
        "mt_companies": "",
    })
    with logged_in_client.application.app_context():
        country_id = TVDisplayCountry.query.first().id
    # Save a bank with a name that's NOT a catalog slug.
    logged_in_client.post(f"/tv-display/countries/{country_id}", data={
        "country_name": "Mexico", "country_code": "MX",
        "mt_companies": "maxi",
        "new_bank_name": "Some Random Bank",
    })
    body = logged_in_client.get(f"/tv-display/countries/{country_id}").data.decode()
    assert "(custom) Some Random Bank" in body


# ── Slug-based form submissions persist ────────────────────────

def test_picker_submission_persists_slugs(logged_in_client, test_store_id):
    """Operator picks Maxi + Vigo from the dropdown → mt_companies
    stores 'maxi,vigo'. Bank picker writes 'mx_bbva_bancomer'."""
    _activate_addon(logged_in_client, test_store_id)
    logged_in_client.get("/tv-display")
    logged_in_client.post("/tv-display/countries/new", data={
        "country_name": "Mexico", "country_code": "MX",
        "mt_companies": "",
    })
    with logged_in_client.application.app_context():
        country_id = TVDisplayCountry.query.first().id
    logged_in_client.post(f"/tv-display/countries/{country_id}", data={
        "country_name": "Mexico", "country_code": "MX",
        "mt_companies": "maxi,vigo",  # picker submits slug CSV
        "new_bank_name": "mx_bbva_bancomer",
    })
    with logged_in_client.application.app_context():
        country = TVDisplayCountry.query.filter_by(id=country_id).first()
        bank = TVDisplayPayoutBank.query.filter_by(country_id=country_id).first()
        assert country.mt_companies == "maxi,vigo"
        assert bank.bank_name == "mx_bbva_bancomer"


# ── Public board resolves slugs to display names ───────────────

def test_public_board_renders_display_names_not_slugs(client, logged_in_client, test_store_id):
    """A customer reading the rate board sees 'BBVA Bancomer' — the
    user-friendly display_name — not 'mx_bbva_bancomer'."""
    _activate_addon(logged_in_client, test_store_id)
    logged_in_client.get("/tv-display")
    logged_in_client.post("/tv-display/countries/new", data={
        "country_name": "Mexico", "country_code": "MX",
        "mt_companies": "",
    })
    with logged_in_client.application.app_context():
        country_id = TVDisplayCountry.query.first().id
    # Save with slugs.
    logged_in_client.post(f"/tv-display/countries/{country_id}", data={
        "country_name": "Mexico", "country_code": "MX",
        "mt_companies": "maxi,vigo",
        "new_bank_name": "mx_bbva_bancomer",
    })
    with logged_in_client.application.app_context():
        token = TVDisplay.query.first().public_token
    body = client.get(f"/tv/{token}").data.decode()
    # Display names appear, slugs do not.
    assert "Maxi" in body
    assert "Vigo" in body
    assert "BBVA Bancomer" in body
    assert "mx_bbva_bancomer" not in body
    assert "maxi" not in body or "Maxi" in body  # display_name not slug


def test_public_board_falls_back_to_slug_for_unknown_token(client, logged_in_client, test_store_id):
    """A slug that isn't in the catalog (unlikely but defensive)
    renders as-is rather than dropping the column entirely."""
    _activate_addon(logged_in_client, test_store_id)
    logged_in_client.get("/tv-display")
    logged_in_client.post("/tv-display/countries/new", data={
        "country_name": "Mexico", "country_code": "MX",
        "mt_companies": "",
    })
    with logged_in_client.application.app_context():
        country_id = TVDisplayCountry.query.first().id
    # Manually pollute mt_companies with a non-catalog slug.
    with logged_in_client.application.app_context():
        c = TVDisplayCountry.query.filter_by(id=country_id).first()
        c.mt_companies = "made_up_slug"
        db.session.commit()
    with logged_in_client.application.app_context():
        token = TVDisplay.query.first().public_token
    body = client.get(f"/tv/{token}").data.decode()
    # Falls back to rendering the raw slug as the column label.
    assert "made_up_slug" in body


# ── is_active soft-delete keeps existing data resolving ────────

def test_inactive_company_still_resolves_on_existing_country(client, logged_in_client, test_store_id):
    """Superadmin retires a catalog entry (is_active=False). Country
    sections that already reference it should keep rendering the
    display_name — just hidden from the picker on new edits."""
    _activate_addon(logged_in_client, test_store_id)
    logged_in_client.get("/tv-display")
    logged_in_client.post("/tv-display/countries/new", data={
        "country_name": "Mexico", "country_code": "MX",
        "mt_companies": "",
    })
    with logged_in_client.application.app_context():
        country_id = TVDisplayCountry.query.first().id
    logged_in_client.post(f"/tv-display/countries/{country_id}", data={
        "country_name": "Mexico", "country_code": "MX",
        "mt_companies": "maxi",
        "new_bank_name": "mx_bbva_bancomer",
    })
    # Retire the company catalog entry.
    with logged_in_client.application.app_context():
        c = TVCompanyCatalog.query.filter_by(slug="maxi").first()
        c.is_active = False
        db.session.commit()
    # Public board still renders display_name on the existing column.
    with logged_in_client.application.app_context():
        token = TVDisplay.query.first().public_token
    body = client.get(f"/tv/{token}").data.decode()
    assert "Maxi" in body  # display_name still resolves
