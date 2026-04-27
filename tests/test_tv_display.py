"""TV Display add-on — covers the model, admin CRUD, public render,
add-on gating, token rotation, superadmin per-store override, and
the brand-consistent theme + orientation contract.

Three audiences in this PR map to three test groups:

  * admin/employee CRUD ("operator" tests)
  * public render at /tv/<token> ("viewer" tests)
  * superadmin override at /superadmin/stores/<id>/addons/<key>/toggle

Plus light/dark theme + orientation propagation, the addon catalog
update (price + status flip), and the retention purge cascade.
"""
from datetime import datetime, timedelta

from app import (
    db, User, Store,
    TVDisplay, TVDisplayCountry, TVDisplayPayoutBank, TVDisplayRate,
    ADDONS_CATALOG, store_has_addon, store_addon_keys,
    _country_flag_emoji, purge_expired_stores,
)


# ── Helpers ────────────────────────────────────────────────────

def _activate_addon(client, store_id):
    """Flip tv_display on for a store via direct DB write (the
    add-on gate blocks the admin-side toggle until they're on a
    paid plan, which complicates these tests)."""
    with client.application.app_context():
        s = db.session.get(Store, store_id)
        s.plan = "basic"
        s.addons = "tv_display"
        db.session.commit()


def _make_display(client, store_id):
    """Set up a country with one bank and one rate so the public
    render has something to draw."""
    _activate_addon(client, store_id)
    client.post("/tv-display/countries/new", data={
        "country_name": "Mexico",
        "country_code": "mx",
        "mt_companies": "Maxi, Cibao, Vigo",
    })
    with client.application.app_context():
        country = TVDisplayCountry.query.first()
        country_id = country.id
    client.post(f"/tv-display/countries/{country_id}", data={
        "country_name": "Mexico", "country_code": "MX",
        "mt_companies": "Maxi, Cibao, Vigo",
        "new_bank_name": "Bancomer",
    })
    with client.application.app_context():
        bank = TVDisplayPayoutBank.query.first()
        bank_id = bank.id
    client.post(f"/tv-display/countries/{country_id}", data={
        "country_name": "Mexico", "country_code": "MX",
        "mt_companies": "Maxi, Cibao, Vigo",
        f"bank-{bank_id}-name": "Bancomer",
        f"bank-{bank_id}-sort": "10",
        f"rate-{bank_id}-0": "18.36",
        f"rate-{bank_id}-1": "18.07",
        f"rate-{bank_id}-2": "18.51",
    })
    with client.application.app_context():
        token = TVDisplay.query.first().public_token
    return {"country_id": country_id, "bank_id": bank_id, "token": token}


def _superadmin_client(application):
    c = application.test_client()
    with application.app_context():
        sa_id = User.query.filter_by(username="superadmin").first().id
    with c.session_transaction() as s:
        s["user_id"] = sa_id; s["role"] = "superadmin"; s["store_id"] = None
    return c


# ── 1. Catalog + helpers ───────────────────────────────────────

def test_addons_catalog_tv_display_priced_5_and_active():
    """tv_display has been graduated from coming_soon → active and
    priced at $5/mo per the pilot agreement. Regression-guard the
    values so we don't accidentally drop the price."""
    addon = ADDONS_CATALOG["tv_display"]
    assert addon["status"] == "active"
    assert addon["price_cents"] == 500
    assert "$5" in addon["price_label"]


def test_country_flag_emoji_helper():
    assert _country_flag_emoji("MX") == "🇲🇽"
    assert _country_flag_emoji("gt") == "🇬🇹"  # case-insensitive
    assert _country_flag_emoji("") == ""
    assert _country_flag_emoji("XYZ") == ""  # invalid length
    assert _country_flag_emoji("M1") == ""   # non-alpha


def test_store_has_addon_helper(client, test_store_id):
    """store_has_addon is the single predicate every gated route
    uses; flipping it must flip the surface."""
    with client.application.app_context():
        s = db.session.get(Store, test_store_id)
        assert store_has_addon(s, "tv_display") is False
        s.addons = "tv_display"; db.session.commit()
        assert store_has_addon(s, "tv_display") is True
        s.addons = ""; db.session.commit()
        assert store_has_addon(s, "tv_display") is False


# ── 2. Admin CRUD ──────────────────────────────────────────────

def test_admin_blocked_when_addon_off(logged_in_client):
    """Without the add-on active, /tv-display 302s to subscription
    so the operator knows where to turn it on."""
    resp = logged_in_client.get("/tv-display")
    assert resp.status_code == 302
    assert "/admin/subscription" in resp.headers["Location"]


def test_admin_landing_renders_when_addon_on(logged_in_client, test_store_id):
    _activate_addon(logged_in_client, test_store_id)
    body = logged_in_client.get("/tv-display").data.decode()
    assert "Public display URL" in body
    assert "Display settings" in body
    assert "Country sections" in body
    # Public token is auto-generated on first visit.
    assert "/tv/" in body


def test_creating_a_country_persists_with_uppercased_code(logged_in_client, test_store_id):
    _activate_addon(logged_in_client, test_store_id)
    logged_in_client.get("/tv-display")  # ensure display exists
    resp = logged_in_client.post("/tv-display/countries/new", data={
        "country_name": "Guatemala",
        "country_code": "gt",
        "mt_companies": "Maxi, Vigo",
    })
    assert resp.status_code == 302
    with logged_in_client.application.app_context():
        c = TVDisplayCountry.query.filter_by(country_name="Guatemala").first()
        assert c is not None
        assert c.country_code == "GT"
        assert c.mt_companies == "Maxi, Vigo"


def test_country_save_persists_full_matrix(logged_in_client, test_store_id):
    """End-to-end: create country → add bank → save 3 rates. All
    three rate rows land in the DB tied to the right (bank, company)."""
    setup = _make_display(logged_in_client, test_store_id)
    with logged_in_client.application.app_context():
        rates = TVDisplayRate.query.filter_by(bank_id=setup["bank_id"]).all()
        rate_map = {r.mt_company: r.rate for r in rates}
        assert rate_map == {"Maxi": 18.36, "Cibao": 18.07, "Vigo": 18.51}


def test_blank_rate_input_deletes_existing_cell(logged_in_client, test_store_id):
    setup = _make_display(logged_in_client, test_store_id)
    # Re-save with one cell blanked out.
    logged_in_client.post(f"/tv-display/countries/{setup['country_id']}", data={
        "country_name": "Mexico", "country_code": "MX",
        "mt_companies": "Maxi, Cibao, Vigo",
        f"bank-{setup['bank_id']}-name": "Bancomer",
        f"bank-{setup['bank_id']}-sort": "10",
        f"rate-{setup['bank_id']}-0": "18.36",
        f"rate-{setup['bank_id']}-1": "",      # cleared
        f"rate-{setup['bank_id']}-2": "18.51",
    })
    with logged_in_client.application.app_context():
        rates = TVDisplayRate.query.filter_by(bank_id=setup["bank_id"]).all()
        assert {r.mt_company for r in rates} == {"Maxi", "Vigo"}


def test_removing_a_column_deletes_orphan_rates(logged_in_client, test_store_id):
    """When the admin drops "Vigo" from the column list, every Vigo
    rate row for that country is purged (otherwise re-adding the
    column would resurrect stale numbers). Uses a subquery delete
    rather than join+delete because SQLAlchemy forbids the latter."""
    setup = _make_display(logged_in_client, test_store_id)
    logged_in_client.post(f"/tv-display/countries/{setup['country_id']}", data={
        "country_name": "Mexico", "country_code": "MX",
        "mt_companies": "Maxi, Cibao",   # Vigo dropped
        f"bank-{setup['bank_id']}-name": "Bancomer",
        f"bank-{setup['bank_id']}-sort": "10",
        f"rate-{setup['bank_id']}-0": "18.40",
        f"rate-{setup['bank_id']}-1": "18.10",
    })
    with logged_in_client.application.app_context():
        rates = TVDisplayRate.query.filter_by(bank_id=setup["bank_id"]).all()
        companies = {r.mt_company for r in rates}
        assert "Vigo" not in companies
        assert companies == {"Maxi", "Cibao"}


def test_bank_delete_checkbox_cascades_rates(logged_in_client, test_store_id):
    setup = _make_display(logged_in_client, test_store_id)
    logged_in_client.post(f"/tv-display/countries/{setup['country_id']}", data={
        "country_name": "Mexico", "country_code": "MX",
        "mt_companies": "Maxi, Cibao, Vigo",
        f"bank-{setup['bank_id']}-delete": "1",
    })
    with logged_in_client.application.app_context():
        assert TVDisplayPayoutBank.query.filter_by(id=setup["bank_id"]).first() is None
        assert TVDisplayRate.query.filter_by(bank_id=setup["bank_id"]).count() == 0


def test_country_delete_cascades_banks_and_rates(logged_in_client, test_store_id):
    setup = _make_display(logged_in_client, test_store_id)
    logged_in_client.post(f"/tv-display/countries/{setup['country_id']}/delete")
    with logged_in_client.application.app_context():
        assert TVDisplayCountry.query.filter_by(id=setup["country_id"]).first() is None
        assert TVDisplayPayoutBank.query.filter_by(country_id=setup["country_id"]).count() == 0
        assert TVDisplayRate.query.filter_by(bank_id=setup["bank_id"]).count() == 0


def test_settings_save_persists_orientation_and_theme(logged_in_client, test_store_id):
    _activate_addon(logged_in_client, test_store_id)
    logged_in_client.get("/tv-display")
    logged_in_client.post("/tv-display/settings", data={
        "title": "Custom Header",
        "subtitle": "ES sub",
        "orientation": "portrait",
        "theme": "dark",
    })
    with logged_in_client.application.app_context():
        d = TVDisplay.query.first()
        assert d.title == "Custom Header"
        assert d.subtitle == "ES sub"
        assert d.orientation == "portrait"
        assert d.theme == "dark"


def test_settings_rejects_invalid_orientation(logged_in_client, test_store_id):
    _activate_addon(logged_in_client, test_store_id)
    logged_in_client.get("/tv-display")
    logged_in_client.post("/tv-display/settings", data={
        "title": "X", "orientation": "diagonal", "theme": "neon",
    })
    with logged_in_client.application.app_context():
        d = TVDisplay.query.first()
        # Both fields fall back to the safe default rather than
        # accepting garbage values.
        assert d.orientation == "auto"
        assert d.theme == "light"


def test_token_regenerate_invalidates_old_url(client, logged_in_client, test_store_id):
    setup = _make_display(logged_in_client, test_store_id)
    old_token = setup["token"]
    # Old URL works.
    assert client.get(f"/tv/{old_token}").status_code == 200
    logged_in_client.post("/tv-display/regenerate-token")
    with logged_in_client.application.app_context():
        new_token = TVDisplay.query.first().public_token
    assert new_token != old_token
    assert client.get(f"/tv/{old_token}").status_code == 404
    assert client.get(f"/tv/{new_token}").status_code == 200


# ── 3. Employee access ─────────────────────────────────────────

def test_employee_can_manage_rates(client, test_store_id):
    """v1 explicitly grants employees /tv-display access — rate
    management is a daily-operations job, not a back-office one."""
    _activate_addon(client, test_store_id)
    from tests.conftest import make_employee_client
    emp = make_employee_client(test_store_id)
    resp = emp.get("/tv-display")
    assert resp.status_code == 200


def test_employee_can_save_rates(client, test_store_id):
    """Defense-in-depth — the URL is reachable and POSTs persist."""
    _activate_addon(client, test_store_id)
    from tests.conftest import make_employee_client
    emp = make_employee_client(test_store_id)
    emp.get("/tv-display")
    resp = emp.post("/tv-display/countries/new", data={
        "country_name": "Honduras", "country_code": "HN",
        "mt_companies": "Maxi, Vigo",
    })
    assert resp.status_code == 302
    with client.application.app_context():
        assert TVDisplayCountry.query.filter_by(country_name="Honduras").first() is not None


# ── 4. Public render ───────────────────────────────────────────

def test_public_render_shows_brand_design_tokens(client, logged_in_client, test_store_id):
    """The public TV page is standalone (no base.html) so we link
    design-tokens.css directly. Regression-guards that the brand
    palette flows in (no Xenok-style deep-blue regressions)."""
    setup = _make_display(logged_in_client, test_store_id)
    body = client.get(f"/tv/{setup['token']}").data.decode()
    assert "design-tokens.css" in body, "must load design tokens"
    assert "--db-neon" in body, "must use neon-green design token"
    assert "Space Grotesk" in body
    assert "JetBrains Mono" in body


def test_public_render_includes_country_section(client, logged_in_client, test_store_id):
    setup = _make_display(logged_in_client, test_store_id)
    body = client.get(f"/tv/{setup['token']}").data.decode()
    assert "Mexico" in body
    assert "Maxi" in body and "Cibao" in body and "Vigo" in body
    assert "Bancomer" in body
    # SVG flag from flag-icons replaces emoji on the public board
    # (emoji flags don't render on Windows / smart-TV browsers).
    assert 'class="fi fi-mx"' in body, "country flag SVG should render"


def test_public_render_splits_dollars_and_cents(client, logged_in_client, test_store_id):
    """Big readable numbers — the rate cell renders $18 with cents
    in superscript, matching the pilot store's layout."""
    setup = _make_display(logged_in_client, test_store_id)
    body = client.get(f"/tv/{setup['token']}").data.decode()
    # 18.36 → <span class="dollar">$</span>18<span class="cents">36</span>
    assert '<span class="dollar">$</span>18<span class="cents">36</span>' in body
    assert '<span class="dollar">$</span>18<span class="cents">07</span>' in body
    assert '<span class="dollar">$</span>18<span class="cents">51</span>' in body


def test_public_render_carries_orientation_attribute(client, logged_in_client, test_store_id):
    setup = _make_display(logged_in_client, test_store_id)
    # Default
    body = client.get(f"/tv/{setup['token']}").data.decode()
    assert 'data-orientation="auto"' in body
    # Force portrait
    logged_in_client.post("/tv-display/settings", data={
        "title": "X", "orientation": "portrait", "theme": "light",
    })
    body = client.get(f"/tv/{setup['token']}").data.decode()
    assert 'data-orientation="portrait"' in body


def test_public_render_carries_theme_attribute_independent_of_user(client, logged_in_client, test_store_id):
    """The TV theme is a separate column from the user's
    theme_preference. Setting the user's app to dark must NOT flip
    the TV — the operator wants control of each independently."""
    setup = _make_display(logged_in_client, test_store_id)
    # User flipped to dark mode (admin app); board stays light by default.
    with logged_in_client.application.app_context():
        admin = User.query.filter_by(username="admin@test.com").first()
        admin.theme_preference = "dark"; db.session.commit()
    body = client.get(f"/tv/{setup['token']}").data.decode()
    assert 'data-theme="light"' in body, \
        "TV theme must follow display.theme, not user.theme_preference"
    # Now flip the BOARD's theme.
    logged_in_client.post("/tv-display/settings", data={
        "title": "X", "orientation": "auto", "theme": "dark",
    })
    body = client.get(f"/tv/{setup['token']}").data.decode()
    assert 'data-theme="dark"' in body


def test_public_returns_404_for_unknown_token(client):
    assert client.get("/tv/totally-bogus-token").status_code == 404


def test_public_returns_404_when_addon_removed(client, logged_in_client, test_store_id):
    setup = _make_display(logged_in_client, test_store_id)
    # Verify it's serving first.
    assert client.get(f"/tv/{setup['token']}").status_code == 200
    # Remove addon.
    with logged_in_client.application.app_context():
        s = db.session.get(Store, test_store_id)
        s.addons = ""; db.session.commit()
    assert client.get(f"/tv/{setup['token']}").status_code == 404


def test_public_includes_auto_refresh_marker(client, logged_in_client, test_store_id):
    """The TV polls itself on a 30s interval and reloads when
    last_updated_at changes. The marker must be in the rendered HTML
    so the polling JS has something to compare against."""
    setup = _make_display(logged_in_client, test_store_id)
    body = client.get(f"/tv/{setup['token']}").data.decode()
    assert 'name="x-tv-last-updated"' in body


# ── 5. Superadmin override ─────────────────────────────────────

def test_superadmin_can_toggle_addon_on_for_any_store(client, test_store_id):
    """Superadmin's per-store toggle bypasses the paid-plan gate
    that the operator-side handler enforces — useful for pilot /
    comped stores."""
    # Pilot store on a trial — operator-side toggle would fail.
    with client.application.app_context():
        s = db.session.get(Store, test_store_id)
        s.plan = "trial"; s.addons = ""
        db.session.commit()
    sa = _superadmin_client(client.application)
    resp = sa.post(f"/superadmin/stores/{test_store_id}/addons/tv_display/toggle")
    assert resp.status_code == 302
    with client.application.app_context():
        s = db.session.get(Store, test_store_id)
        assert "tv_display" in s.addons


def test_superadmin_toggle_off(client, test_store_id):
    with client.application.app_context():
        s = db.session.get(Store, test_store_id)
        s.addons = "tv_display"; db.session.commit()
    sa = _superadmin_client(client.application)
    sa.post(f"/superadmin/stores/{test_store_id}/addons/tv_display/toggle")
    with client.application.app_context():
        s = db.session.get(Store, test_store_id)
        assert "tv_display" not in (s.addons or "")


def test_superadmin_toggle_unknown_addon_flashes_and_redirects(client, test_store_id):
    sa = _superadmin_client(client.application)
    resp = sa.post(f"/superadmin/stores/{test_store_id}/addons/wat/toggle",
                    follow_redirects=True)
    assert resp.status_code == 200
    assert b"Unknown add-on" in resp.data


def test_superadmin_toggle_writes_audit(client, test_store_id):
    sa = _superadmin_client(client.application)
    sa.post(f"/superadmin/stores/{test_store_id}/addons/tv_display/toggle")
    from app import SuperadminAuditLog
    with client.application.app_context():
        row = (SuperadminAuditLog.query
               .filter(SuperadminAuditLog.action.in_(("add_addon", "remove_addon")))
               .first())
        assert row is not None
        assert row.details == "tv_display"


def test_non_superadmin_cannot_hit_override_endpoint(logged_in_client, test_store_id):
    resp = logged_in_client.post(
        f"/superadmin/stores/{test_store_id}/addons/tv_display/toggle")
    assert resp.status_code in (302, 403, 404)


# ── 6. Sidebar nav link ────────────────────────────────────────

def test_sidebar_shows_tv_display_link_when_addon_active(logged_in_client, test_store_id):
    _activate_addon(logged_in_client, test_store_id)
    body = logged_in_client.get("/dashboard").data.decode()
    assert "/tv-display" in body
    assert "TV Display" in body


def test_sidebar_hides_tv_display_link_when_addon_off(logged_in_client):
    """Default fixture state has the addon off; nav link must not
    appear so we don't tease users with a feature they haven't
    purchased."""
    body = logged_in_client.get("/dashboard").data.decode()
    assert ">TV Display</a>" not in body


# ── 7. Retention purge cascade ─────────────────────────────────

def test_purge_cascades_through_tv_display_chain(client):
    """When a store is purged, its TVDisplay → Country → Bank →
    Rate chain has to be cleaned up before the User delete. None
    of these tables have a direct store_id column except TVDisplay,
    so we walk the chain explicitly in purge_expired_stores()."""
    with client.application.app_context():
        s = Store(name="Doomed TV", slug="doomed-tv-x", plan="inactive",
                   is_active=False,
                   data_retention_until=datetime.utcnow() - timedelta(days=1))
        db.session.add(s); db.session.flush()
        d = TVDisplay(store_id=s.id, public_token="doomed-token-zzz")
        db.session.add(d); db.session.flush()
        c = TVDisplayCountry(display_id=d.id, country_name="DoomedLand",
                              mt_companies="A,B")
        db.session.add(c); db.session.flush()
        bank = TVDisplayPayoutBank(country_id=c.id, bank_name="Bonk")
        db.session.add(bank); db.session.flush()
        rate = TVDisplayRate(bank_id=bank.id, mt_company="A", rate=10.0)
        db.session.add(rate); db.session.commit()
        d_id, c_id, b_id, r_id = d.id, c.id, bank.id, rate.id

        n = purge_expired_stores()
        assert n == 1
        assert db.session.get(TVDisplay, d_id) is None
        assert db.session.get(TVDisplayCountry, c_id) is None
        assert db.session.get(TVDisplayPayoutBank, b_id) is None
        assert db.session.get(TVDisplayRate, r_id) is None


# ── 8. _ensure_tv_display idempotency ──────────────────────────

def test_ensure_tv_display_creates_once_with_unique_token(logged_in_client, test_store_id):
    """Hitting /tv-display twice should not create two display rows;
    the GET is idempotent."""
    _activate_addon(logged_in_client, test_store_id)
    logged_in_client.get("/tv-display")
    logged_in_client.get("/tv-display")
    with logged_in_client.application.app_context():
        assert TVDisplay.query.filter_by(store_id=test_store_id).count() == 1
