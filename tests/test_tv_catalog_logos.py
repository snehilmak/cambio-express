"""TV Catalog logo storage + rendering — Phase 2 of the logo rollout.

Covers:
  - Upload endpoint: mime-type whitelist, size cap, slug match,
    superadmin-only, audit-log entry.
  - Serve route: streams the right bytes, sets cache headers,
    404s on unknown / wrong type / missing.
  - Cache-bust contract: URLs include ?v=<unix> only when a logo
    has been uploaded.
  - Editor pickers + public board both render logos when present
    and gracefully fall back to text otherwise.
"""
import io

from app import (
    db, User, Store, TVDisplay, TVDisplayCountry, TVDisplayPayoutBank,
    TVCompanyCatalog, TVBankCatalog, TVCatalogLogo,
)


# ── Helpers ────────────────────────────────────────────────────

# Smallest possible PNG — 67 bytes, 1×1 transparent pixel. Real
# uploads will be 5-50 KB but we only need a valid PNG header for
# the mime-validation path.
TINY_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00"
    b"\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\rIDAT"
    b"x\x9cc\xf8\xff\xff?\x00\x05\xfe\x02\xfeA\xc8z\xc1\x00\x00\x00"
    b"\x00IEND\xaeB`\x82"
)


def _superadmin_client(application):
    """Logged-in superadmin client. Bypasses the password / 2FA flow
    by writing the session directly — same pattern other test files
    use for superadmin actions."""
    c = application.test_client()
    with application.app_context():
        sa = User.query.filter_by(username="superadmin").first()
        sa_id = sa.id
    with c.session_transaction() as s:
        s["user_id"] = sa_id
        s["role"]    = "superadmin"
        s["store_id"] = None
    return c


def _activate_addon(client, store_id):
    with client.application.app_context():
        s = db.session.get(Store, store_id)
        s.plan   = "basic"
        s.addons = "tv_display"
        db.session.commit()


def _upload(client, catalog_type, slug, *, mime="image/png", body=TINY_PNG, filename="logo.png"):
    """POST /superadmin/tv-catalog/<type>/<slug>/logo as multipart."""
    return client.post(
        f"/superadmin/tv-catalog/{catalog_type}/{slug}/logo",
        data={"logo": (io.BytesIO(body), filename, mime)},
        content_type="multipart/form-data",
        follow_redirects=False,
    )


# ── Upload endpoint ────────────────────────────────────────────

def test_upload_persists_blob_with_mime(client):
    sa = _superadmin_client(client.application)
    resp = _upload(sa, "company", "intermex")
    assert resp.status_code == 302  # flash + redirect

    with client.application.app_context():
        row = TVCatalogLogo.query.filter_by(
            catalog_type="company", slug="intermex").first()
        assert row is not None
        assert row.mime_type == "image/png"
        assert row.blob == TINY_PNG
        assert row.file_size == len(TINY_PNG)


def test_upload_mirrors_logo_url_to_parent_catalog_row(client):
    sa = _superadmin_client(client.application)
    _upload(sa, "company", "intermex")
    with client.application.app_context():
        cat = TVCompanyCatalog.query.filter_by(slug="intermex").first()
        # logo_url mirrors the public serve path so other code paths
        # can resolve it without a TVCatalogLogo lookup.
        assert "/tv/logo/company/intermex" in cat.logo_url


def test_upload_re_upload_replaces_blob_and_bumps_updated_at(client):
    sa = _superadmin_client(client.application)
    _upload(sa, "company", "intermex")
    with client.application.app_context():
        first = TVCatalogLogo.query.filter_by(slug="intermex").first()
        first_updated = first.updated_at

    # Re-upload a slightly different PNG (same first byte sequence,
    # different IDAT — works for our test purposes).
    new_body = TINY_PNG + b"\x00\x00"
    _upload(sa, "company", "intermex", body=new_body)
    with client.application.app_context():
        row = TVCatalogLogo.query.filter_by(slug="intermex").first()
        assert row.blob == new_body
        # No new row was inserted — same id, just bumped.
        assert TVCatalogLogo.query.filter_by(slug="intermex").count() == 1
        assert row.updated_at >= first_updated


def test_upload_rejects_unknown_mime(client):
    sa = _superadmin_client(client.application)
    resp = _upload(sa, "company", "intermex",
                    mime="application/octet-stream", filename="logo.bin")
    assert resp.status_code == 302  # flash + redirect (with error)
    with client.application.app_context():
        assert TVCatalogLogo.query.filter_by(slug="intermex").first() is None


def test_upload_rejects_oversized_file(client):
    """200 KiB hard cap. 250 KiB body is rejected."""
    sa = _superadmin_client(client.application)
    big = b"x" * (250 * 1024)
    resp = _upload(sa, "company", "intermex", body=big)
    assert resp.status_code == 302
    with client.application.app_context():
        assert TVCatalogLogo.query.filter_by(slug="intermex").first() is None


def test_upload_rejects_empty_file(client):
    sa = _superadmin_client(client.application)
    resp = _upload(sa, "company", "intermex", body=b"")
    assert resp.status_code == 302
    with client.application.app_context():
        assert TVCatalogLogo.query.filter_by(slug="intermex").first() is None


def test_upload_rejects_unknown_slug(client):
    sa = _superadmin_client(client.application)
    resp = _upload(sa, "company", "totally-not-real")
    assert resp.status_code == 302
    with client.application.app_context():
        assert TVCatalogLogo.query.filter_by(slug="totally-not-real").first() is None


def test_upload_rejects_invalid_catalog_type(client):
    sa = _superadmin_client(client.application)
    resp = _upload(sa, "wat", "intermex")
    assert resp.status_code == 404


def test_upload_blocks_non_superadmin(logged_in_client):
    """Store admin can't reach the upload endpoint."""
    resp = _upload(logged_in_client, "company", "intermex")
    # Decorator redirects unauthorized users; either redirect or
    # 403 / 404 is acceptable, but it must NOT persist a row.
    assert resp.status_code in (302, 403, 404)
    with logged_in_client.application.app_context():
        assert TVCatalogLogo.query.filter_by(slug="intermex").first() is None


def test_upload_writes_audit_entry(client):
    from app import SuperadminAuditLog
    sa = _superadmin_client(client.application)
    _upload(sa, "company", "intermex")
    with client.application.app_context():
        row = (SuperadminAuditLog.query
               .filter_by(action="tv_logo_upload").first())
        assert row is not None
        assert "intermex" in row.details


# ── Serve route ────────────────────────────────────────────────

def test_serve_returns_blob_with_long_cache(client):
    sa = _superadmin_client(client.application)
    _upload(sa, "company", "intermex")
    resp = client.get("/tv/logo/company/intermex")
    assert resp.status_code == 200
    assert resp.data == TINY_PNG
    assert resp.headers["Content-Type"] == "image/png"
    assert "max-age=31536000" in resp.headers["Cache-Control"]
    assert "immutable" in resp.headers["Cache-Control"]
    assert resp.headers["X-Content-Type-Options"] == "nosniff"


def test_serve_404s_on_unknown_slug(client):
    assert client.get("/tv/logo/company/nope").status_code == 404


def test_serve_404s_on_invalid_catalog_type(client):
    assert client.get("/tv/logo/wat/intermex").status_code == 404


def test_serve_404s_when_mime_corrupted(client):
    """Defense in depth: even if a row gets persisted with a bogus
    mime (e.g. via a database-level edit), the serve route refuses
    rather than handing arbitrary bytes to a browser."""
    sa = _superadmin_client(client.application)
    _upload(sa, "company", "intermex")
    with client.application.app_context():
        row = TVCatalogLogo.query.filter_by(slug="intermex").first()
        row.mime_type = "application/x-evil"
        db.session.commit()
    assert client.get("/tv/logo/company/intermex").status_code == 404


# ── Editor renders logos ───────────────────────────────────────

def test_editor_chip_renders_logo_when_uploaded(logged_in_client, test_store_id):
    """Country editor's column-header chips show the logo thumbnail
    next to the display name."""
    sa = _superadmin_client(logged_in_client.application)
    _upload(sa, "company", "maxi")

    _activate_addon(logged_in_client, test_store_id)
    logged_in_client.get("/tv-display")
    logged_in_client.post("/tv-display/countries/new", data={
        "country_name": "Mexico", "country_code": "MX",
        "mt_companies": "maxi",
    })
    with logged_in_client.application.app_context():
        country_id = TVDisplayCountry.query.first().id

    body = logged_in_client.get(f"/tv-display/countries/{country_id}").data.decode()
    assert "ce-chip-logo" in body
    assert "/tv/logo/company/maxi" in body


def test_editor_chip_falls_back_to_text_without_logo(logged_in_client, test_store_id):
    """Catalog entries without an uploaded logo render text-only —
    no broken-image icons, no placeholders."""
    _activate_addon(logged_in_client, test_store_id)
    logged_in_client.get("/tv-display")
    logged_in_client.post("/tv-display/countries/new", data={
        "country_name": "Mexico", "country_code": "MX",
        "mt_companies": "maxi",
    })
    with logged_in_client.application.app_context():
        country_id = TVDisplayCountry.query.first().id
    body = logged_in_client.get(f"/tv-display/countries/{country_id}").data.decode()
    assert "Maxi" in body  # display_name still rendered
    # No chip-logo wrapper since no upload happened.
    assert 'class="ce-chip-logo"' not in body


def test_editor_bank_row_renders_logo_thumbnail(logged_in_client, test_store_id):
    sa = _superadmin_client(logged_in_client.application)
    _upload(sa, "bank", "mx_bbva_bancomer")

    _activate_addon(logged_in_client, test_store_id)
    logged_in_client.get("/tv-display")
    logged_in_client.post("/tv-display/countries/new", data={
        "country_name": "Mexico", "country_code": "MX",
        "mt_companies": "maxi",
    })
    with logged_in_client.application.app_context():
        country_id = TVDisplayCountry.query.first().id
    logged_in_client.post(f"/tv-display/countries/{country_id}", data={
        "country_name": "Mexico", "country_code": "MX",
        "mt_companies": "maxi",
        "new_bank_name": "mx_bbva_bancomer",
    })
    body = logged_in_client.get(f"/tv-display/countries/{country_id}").data.decode()
    assert "ce-bank-logo" in body
    assert "/tv/logo/bank/mx_bbva_bancomer" in body


# ── Public board renders logos ─────────────────────────────────

def test_public_board_renders_company_logos(client, logged_in_client, test_store_id):
    sa = _superadmin_client(logged_in_client.application)
    _upload(sa, "company", "maxi")

    _activate_addon(logged_in_client, test_store_id)
    logged_in_client.get("/tv-display")
    logged_in_client.post("/tv-display/countries/new", data={
        "country_name": "Mexico", "country_code": "MX",
        "mt_companies": "maxi",
    })
    with logged_in_client.application.app_context():
        country_id = TVDisplayCountry.query.first().id
        token = TVDisplay.query.first().public_token
    logged_in_client.post(f"/tv-display/countries/{country_id}", data={
        "country_name": "Mexico", "country_code": "MX",
        "mt_companies": "maxi",
        "new_bank_name": "mx_bbva_bancomer",
    })

    body = client.get(f"/tv/{token}").data.decode()
    assert 'class="tv-col-logo"' in body
    assert "/tv/logo/company/maxi" in body


def test_public_board_renders_bank_logos(client, logged_in_client, test_store_id):
    sa = _superadmin_client(logged_in_client.application)
    _upload(sa, "bank", "mx_bbva_bancomer")

    _activate_addon(logged_in_client, test_store_id)
    logged_in_client.get("/tv-display")
    logged_in_client.post("/tv-display/countries/new", data={
        "country_name": "Mexico", "country_code": "MX",
        "mt_companies": "maxi",
    })
    with logged_in_client.application.app_context():
        country_id = TVDisplayCountry.query.first().id
        token = TVDisplay.query.first().public_token
    logged_in_client.post(f"/tv-display/countries/{country_id}", data={
        "country_name": "Mexico", "country_code": "MX",
        "mt_companies": "maxi",
        "new_bank_name": "mx_bbva_bancomer",
    })

    body = client.get(f"/tv/{token}").data.decode()
    assert 'class="tv-bank-logo"' in body
    assert "/tv/logo/bank/mx_bbva_bancomer" in body


def test_public_board_falls_back_to_text_for_logoless_entries(
        client, logged_in_client, test_store_id):
    """Mix of logo-uploaded + logoless entries renders cleanly:
    logos for what's uploaded, display_name text for the rest."""
    sa = _superadmin_client(logged_in_client.application)
    _upload(sa, "company", "maxi")  # only Maxi has a logo
    # Vigo intentionally not uploaded.

    _activate_addon(logged_in_client, test_store_id)
    logged_in_client.get("/tv-display")
    logged_in_client.post("/tv-display/countries/new", data={
        "country_name": "Mexico", "country_code": "MX",
        "mt_companies": "maxi,vigo",
    })
    with logged_in_client.application.app_context():
        token = TVDisplay.query.first().public_token

    body = client.get(f"/tv/{token}").data.decode()
    assert "/tv/logo/company/maxi" in body  # Maxi: image
    # Vigo: no image, display_name text instead.
    assert "Vigo" in body
    # Defensive: no broken /tv/logo/company/vigo URL leaking
    # (would happen if the route emitted URLs for missing logos).
    assert "/tv/logo/company/vigo" not in body


def test_logo_url_includes_cache_bust_query(logged_in_client, test_store_id):
    """Templates emit ?v=<updated_at_unix> on the logo URL so a
    re-upload busts browser/CDN caches."""
    sa = _superadmin_client(logged_in_client.application)
    _upload(sa, "company", "intermex")

    _activate_addon(logged_in_client, test_store_id)
    logged_in_client.get("/tv-display")
    logged_in_client.post("/tv-display/countries/new", data={
        "country_name": "Mexico", "country_code": "MX",
        "mt_companies": "intermex",
    })
    with logged_in_client.application.app_context():
        country_id = TVDisplayCountry.query.first().id
    body = logged_in_client.get(f"/tv-display/countries/{country_id}").data.decode()
    # ?v= is non-empty; the exact unix timestamp varies per run.
    import re
    m = re.search(r"/tv/logo/company/intermex\?v=(\d+)", body)
    assert m, "logo URL must include cache-bust ?v=<unix>"
    assert int(m.group(1)) > 0


# ── Edit + create endpoints ────────────────────────────────────

def test_edit_renames_display_but_preserves_slug(client):
    sa = _superadmin_client(client.application)
    resp = sa.post("/superadmin/tv-catalog/company/maxi/edit", data={
        "display_name": "Maxi (Renamed)",
        "sort_order":   "5",
        "is_active":    "1",
    })
    assert resp.status_code == 302
    with client.application.app_context():
        row = TVCompanyCatalog.query.filter_by(slug="maxi").first()
        assert row.display_name == "Maxi (Renamed)"
        assert row.sort_order == 5
        # Slug intentionally not editable; still "maxi".
        assert row.slug == "maxi"


def test_edit_soft_deletes_via_active_checkbox(client):
    sa = _superadmin_client(client.application)
    sa.post("/superadmin/tv-catalog/company/maxi/edit", data={
        "display_name": "Maxi",
        "sort_order":   "20",
        # is_active not present → unchecked → soft-delete.
    })
    with client.application.app_context():
        row = TVCompanyCatalog.query.filter_by(slug="maxi").first()
        assert row.is_active is False


def test_create_new_company(client):
    sa = _superadmin_client(client.application)
    resp = sa.post("/superadmin/tv-catalog/new", data={
        "catalog_type": "company",
        "slug":         "remitly",
        "display_name": "Remitly",
    })
    assert resp.status_code == 302
    with client.application.app_context():
        row = TVCompanyCatalog.query.filter_by(slug="remitly").first()
        assert row is not None
        assert row.display_name == "Remitly"
        assert row.is_active is True


def test_create_rejects_duplicate_slug(client):
    sa = _superadmin_client(client.application)
    sa.post("/superadmin/tv-catalog/new", data={
        "catalog_type": "company",
        "slug":         "maxi",  # already in seed
        "display_name": "Should Fail",
    })
    with client.application.app_context():
        # No second row created — the seed entry survives.
        rows = TVCompanyCatalog.query.filter_by(slug="maxi").all()
        assert len(rows) == 1
        assert rows[0].display_name == "Maxi"  # unchanged


def test_create_bank_requires_country_code(client):
    sa = _superadmin_client(client.application)
    sa.post("/superadmin/tv-catalog/new", data={
        "catalog_type": "bank",
        "slug":         "fictional_bank",
        "display_name": "Fictional Bank",
        # country_code missing
    })
    with client.application.app_context():
        assert TVBankCatalog.query.filter_by(slug="fictional_bank").first() is None


def test_create_normalizes_slug_to_safe_chars(client):
    sa = _superadmin_client(client.application)
    sa.post("/superadmin/tv-catalog/new", data={
        "catalog_type": "company",
        "slug":         "Some Brand With Spaces!",
        "display_name": "Some Brand",
    })
    with client.application.app_context():
        # Spaces + ! stripped; uppercase lowercased.
        row = TVCompanyCatalog.query.filter_by(
            slug="somebrandwithspaces").first()
        assert row is not None
