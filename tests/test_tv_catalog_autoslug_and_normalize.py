"""Auto-slug + Pillow logo normalization — Phase 4 of the TV
catalog rollout.

The operator now only provides display_name (+ country_code for
banks); slugs are derived server-side. Logos uploaded through the
UI or dropped into the seed-disk directory are normalized to a
600x200 transparent canvas (PNG) so every catalog entry renders
at the same visual weight on the public TV board.
"""
import io

from app import (
    db, app as flask_app,
    Store, User,
    TVCompanyCatalog, TVBankCatalog, TVCatalogLogo,
    _slugify_catalog_name, _slugify_bank_name, _next_unique_slug,
    _normalize_logo_blob,
    _TV_LOGO_CANVAS_WIDTH, _TV_LOGO_CANVAS_HEIGHT,
)


# ── Helpers (same superadmin client pattern other test files use) ─────

def _superadmin_client(application):
    c = application.test_client()
    with application.app_context():
        sa_id = User.query.filter_by(username="superadmin").first().id
    with c.session_transaction() as s:
        s["user_id"] = sa_id
        s["role"]    = "superadmin"
        s["store_id"] = None
    return c


# ── _slugify_catalog_name ─────────────────────────────────────────────

def test_slugify_basic_lowercase_underscore():
    assert _slugify_catalog_name("BBVA Bancomer") == "bbva_bancomer"
    assert _slugify_catalog_name("RIA Money Transfer") == "ria_money_transfer"


def test_slugify_strips_accents():
    """México renders as 'mexico' not 'm_xico' — important since
    Spanish brand names commonly use ñ/é/á."""
    assert _slugify_catalog_name("Banamex México") == "banamex_mexico"
    assert _slugify_catalog_name("Banco Cuscatlán") == "banco_cuscatlan"


def test_slugify_collapses_punctuation():
    assert _slugify_catalog_name("Cibao Express, S.A.") == "cibao_express_s_a"
    assert _slugify_catalog_name("Boss Revolution!!!") == "boss_revolution"


def test_slugify_caps_at_60_chars():
    long_name = "A" * 200
    out = _slugify_catalog_name(long_name)
    assert len(out) <= 60


def test_slugify_returns_empty_for_empty_input():
    assert _slugify_catalog_name("") == ""
    assert _slugify_catalog_name(None) == ""


def test_slugify_bank_prefixes_country():
    """Banks slug as <iso2>_<name> — same display name in two
    countries gets distinct slugs."""
    assert _slugify_bank_name("Banco Industrial", "GT") == "gt_banco_industrial"
    assert _slugify_bank_name("BAC Credomatic", "HN") == "hn_bac_credomatic"
    # Country code lowercased.
    assert _slugify_bank_name("Banpais", "hn") == "hn_banpais"


def test_slugify_bank_no_country_falls_back():
    """No country code → just the name slug, no prefix."""
    assert _slugify_bank_name("Banpais", "") == "banpais"


# ── _next_unique_slug (collision dedup) ───────────────────────────────

def test_next_unique_slug_returns_base_when_free(client):
    """Slug is not in any catalog → returns it unchanged."""
    with flask_app.app_context():
        out = _next_unique_slug("company", "fresh_brand_no_collision")
        assert out == "fresh_brand_no_collision"


def test_next_unique_slug_appends_suffix_on_collision(client):
    """maxi already exists in the seed; second add gets _2."""
    with flask_app.app_context():
        out = _next_unique_slug("company", "maxi")
        assert out == "maxi_2"


def test_next_unique_slug_increments_past_existing_suffixes(client):
    """If maxi AND maxi_2 both exist, next free is maxi_3."""
    with flask_app.app_context():
        db.session.add(TVCompanyCatalog(
            slug="maxi_2", display_name="Maxi (clone)",
            sort_order=999, is_active=True,
        ))
        db.session.commit()
        out = _next_unique_slug("company", "maxi")
        assert out == "maxi_3"


# ── End-to-end: create-via-form auto-derives slug ────────────────────

def test_create_company_derives_slug_server_side(client):
    """Operator POSTs only display_name; route derives the slug."""
    sa = _superadmin_client(client.application)
    sa.post("/superadmin/tv-catalog/new", data={
        "catalog_type": "company",
        "display_name": "Remitly Money Transfer",
    })
    with client.application.app_context():
        row = TVCompanyCatalog.query.filter_by(
            slug="remitly_money_transfer").first()
        assert row is not None
        assert row.display_name == "Remitly Money Transfer"


def test_create_company_dedupes_collision(client):
    """Adding 'Maxi' a second time produces 'maxi_2' rather than
    failing — operator's typo / duplicate doesn't crash the form."""
    sa = _superadmin_client(client.application)
    sa.post("/superadmin/tv-catalog/new", data={
        "catalog_type": "company",
        "display_name": "Maxi",  # already exists in seed as 'maxi'
    })
    with client.application.app_context():
        clone = TVCompanyCatalog.query.filter_by(slug="maxi_2").first()
        assert clone is not None
        # Original is untouched.
        original = TVCompanyCatalog.query.filter_by(slug="maxi").first()
        assert original.display_name == "Maxi"


def test_create_bank_derives_country_prefixed_slug(client):
    sa = _superadmin_client(client.application)
    sa.post("/superadmin/tv-catalog/new", data={
        "catalog_type": "bank",
        "display_name": "Pichincha",
        "country_code": "EC",
    })
    with client.application.app_context():
        row = TVBankCatalog.query.filter_by(slug="ec_pichincha").first()
        assert row is not None
        assert row.country_code == "EC"


def test_create_bank_handles_accents(client):
    """Accents stripped, slug stays ASCII-safe."""
    sa = _superadmin_client(client.application)
    sa.post("/superadmin/tv-catalog/new", data={
        "catalog_type": "bank",
        "display_name": "Banco Atlántico Sur",
        "country_code": "PE",
    })
    with client.application.app_context():
        row = TVBankCatalog.query.filter_by(
            slug="pe_banco_atlantico_sur").first()
        assert row is not None


def test_create_company_blank_display_name_fails(client):
    sa = _superadmin_client(client.application)
    sa.post("/superadmin/tv-catalog/new", data={
        "catalog_type": "company",
        "display_name": "",
    })
    with client.application.app_context():
        # No row created.
        assert TVCompanyCatalog.query.count() == 12  # seed default


def test_create_bank_missing_country_fails(client):
    sa = _superadmin_client(client.application)
    sa.post("/superadmin/tv-catalog/new", data={
        "catalog_type": "bank",
        "display_name": "Some Bank",
        # No country_code
    })
    with client.application.app_context():
        assert TVBankCatalog.query.filter_by(slug="some_bank").first() is None


# ── Pillow logo normalization ────────────────────────────────────────

def _png_bytes(width, height, color=(255, 0, 0, 255)):
    """Manufacture a tiny PNG of the given size + color for tests."""
    from PIL import Image
    img = Image.new("RGBA", (width, height), color)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def test_normalize_raster_fits_to_canvas():
    """Any raster input comes out at exactly 600x200 RGBA PNG.
    Source's natural dimensions are scaled-and-padded to fit."""
    from PIL import Image
    src = _png_bytes(100, 100)  # square source
    out_blob, out_mime = _normalize_logo_blob(src, "image/png")
    assert out_mime == "image/png"
    out_img = Image.open(io.BytesIO(out_blob))
    assert out_img.size == (_TV_LOGO_CANVAS_WIDTH, _TV_LOGO_CANVAS_HEIGHT)
    assert out_img.mode == "RGBA"


def test_normalize_handles_wide_logo():
    """800x100 wide wordmark → fits within 600 wide, padded vertically."""
    from PIL import Image
    src = _png_bytes(800, 100)
    out_blob, _ = _normalize_logo_blob(src, "image/png")
    out_img = Image.open(io.BytesIO(out_blob))
    assert out_img.size == (600, 200)


def test_normalize_handles_tall_logo():
    """100x400 tall mark → fits within 200 tall, padded horizontally."""
    from PIL import Image
    src = _png_bytes(100, 400)
    out_blob, _ = _normalize_logo_blob(src, "image/png")
    out_img = Image.open(io.BytesIO(out_blob))
    assert out_img.size == (600, 200)


def test_normalize_jpeg_becomes_png():
    """JPEG input (no alpha) → output is PNG with transparent
    surrounding canvas."""
    from PIL import Image
    src_img = Image.new("RGB", (200, 200), (200, 100, 50))
    buf = io.BytesIO()
    src_img.save(buf, format="JPEG")
    src_bytes = buf.getvalue()

    out_blob, out_mime = _normalize_logo_blob(src_bytes, "image/jpeg")
    assert out_mime == "image/png"  # mime upgraded to PNG
    out_img = Image.open(io.BytesIO(out_blob))
    assert out_img.mode == "RGBA"
    assert out_img.size == (600, 200)


def test_normalize_svg_passes_through_untouched():
    """SVG bytes + mime are returned exactly as-is — no Pillow
    rasterization, since SVG's whole point is lossless scaling."""
    svg = b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><rect width="50" height="50"/></svg>'
    out_blob, out_mime = _normalize_logo_blob(svg, "image/svg+xml")
    assert out_blob == svg
    assert out_mime == "image/svg+xml"


def test_normalize_falls_back_on_corrupt_input():
    """Garbage bytes that aren't a valid image → returned unchanged
    rather than blocking the upload with a stack trace. The
    serve-route's mime whitelist + the upload-side mime check
    are what protect the rendering, not this normalizer."""
    junk = b"this is not actually a png file"
    out_blob, out_mime = _normalize_logo_blob(junk, "image/png")
    assert out_blob == junk
    assert out_mime == "image/png"


# ── End-to-end: upload routes through normalization ───────────────────

def test_upload_via_route_normalizes(client):
    """Operator uploads a 100x100 PNG via the superadmin form;
    persisted blob is the 600x200 normalized version."""
    sa = _superadmin_client(client.application)
    src = _png_bytes(100, 100)
    sa.post(
        "/superadmin/tv-catalog/company/intermex/logo",
        data={"logo": (io.BytesIO(src), "intermex.png", "image/png")},
        content_type="multipart/form-data",
    )
    with client.application.app_context():
        from PIL import Image
        row = TVCatalogLogo.query.filter_by(slug="intermex").first()
        assert row is not None
        out_img = Image.open(io.BytesIO(row.blob))
        assert out_img.size == (600, 200)
        assert row.mime_type == "image/png"
        assert row.file_size == len(row.blob)


def test_upload_svg_via_route_passes_through(client):
    """SVG upload reaches the DB unchanged."""
    sa = _superadmin_client(client.application)
    svg = b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10"><rect/></svg>'
    sa.post(
        "/superadmin/tv-catalog/company/maxi/logo",
        data={"logo": (io.BytesIO(svg), "maxi.svg", "image/svg+xml")},
        content_type="multipart/form-data",
    )
    with client.application.app_context():
        row = TVCatalogLogo.query.filter_by(slug="maxi").first()
        assert row.mime_type == "image/svg+xml"
        assert row.blob == svg
