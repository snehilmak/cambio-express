"""TV catalog seed helpers — country-code backfill + disk-import
of logo files. Both run from init_db() on every boot; tests pin
the safety + idempotency invariants both rely on."""
import os

from app import (
    db, app as flask_app,
    TVDisplay, TVDisplayCountry, Store, User,
    TVCompanyCatalog, TVBankCatalog, TVCatalogLogo,
    _backfill_tv_country_codes, _seed_tv_logos_from_disk,
)


# ── Country-code backfill ──────────────────────────────────────

def _make_legacy_country(name, code=None):
    """Create a TVDisplayCountry with no country_code (legacy data)
    so the backfill has something to fix. Returns the row's id."""
    with flask_app.app_context():
        # Need a store + display to attach the country to.
        store = Store.query.filter_by(slug="test-store").first()
        if not TVDisplay.query.filter_by(store_id=store.id).first():
            d = TVDisplay(store_id=store.id, public_token="seed-token-xx")
            db.session.add(d); db.session.commit()
        display = TVDisplay.query.filter_by(store_id=store.id).first()
        c = TVDisplayCountry(
            display_id=display.id,
            country_name=name,
            country_code=code or "",
            mt_companies="",
        )
        db.session.add(c)
        db.session.commit()
        return c.id


def test_backfill_fills_missing_iso_for_known_country(client):
    cid = _make_legacy_country("Mexico")
    fixed = _backfill_tv_country_codes()
    assert fixed >= 1
    with client.application.app_context():
        c = db.session.get(TVDisplayCountry, cid)
        assert c.country_code == "MX"


def test_backfill_handles_synonyms(client):
    cid = _make_legacy_country("Republica Dominicana")
    _backfill_tv_country_codes()
    with client.application.app_context():
        c = db.session.get(TVDisplayCountry, cid)
        assert c.country_code == "DO"


def test_backfill_skips_already_coded_rows(client):
    """Country with an existing country_code shouldn't be touched
    even if the name doesn't match the picker — operator intent
    wins over heuristic matching."""
    cid = _make_legacy_country("Sealand", code="ZZ")
    _backfill_tv_country_codes()
    with client.application.app_context():
        c = db.session.get(TVDisplayCountry, cid)
        # Code unchanged.
        assert c.country_code == "ZZ"


def test_backfill_skips_unknown_country_names(client):
    """A legacy name that doesn't match any picker entry stays
    blank — better to leave it for an operator to fix manually
    than guess wrong."""
    cid = _make_legacy_country("Atlantis")  # not in picker
    _backfill_tv_country_codes()
    with client.application.app_context():
        c = db.session.get(TVDisplayCountry, cid)
        assert c.country_code == ""


def test_backfill_is_idempotent(client):
    """Running twice in a row makes no further changes — the second
    pass returns 0 fixed rows."""
    _make_legacy_country("Mexico")
    first = _backfill_tv_country_codes()
    second = _backfill_tv_country_codes()
    assert first >= 1
    assert second == 0


# ── Seed-logos disk loader ─────────────────────────────────────

def _seed_dir():
    return os.path.join(flask_app.root_path, "static", "seed-logos")


def _drop_logo(catalog_type, slug, ext, body):
    """Plant a fake logo file in the seed directory. Returns the
    full path so the test can clean up afterward."""
    sub = "companies" if catalog_type == "company" else "banks"
    full_dir = os.path.join(_seed_dir(), sub)
    os.makedirs(full_dir, exist_ok=True)
    path = os.path.join(full_dir, f"{slug}.{ext}")
    with open(path, "wb") as fh:
        fh.write(body)
    return path


def _cleanup(path):
    if os.path.exists(path):
        try: os.unlink(path)
        except OSError: pass


def test_seed_disk_imports_known_slug_with_blob(client):
    """A file named after an existing catalog slug gets imported
    on the next call."""
    path = _drop_logo("company", "intermex", "png",
                      b"\x89PNG\r\n\x1a\n" + b"x" * 200)
    try:
        with flask_app.app_context():
            n = _seed_tv_logos_from_disk()
        assert n >= 1
        with client.application.app_context():
            row = TVCatalogLogo.query.filter_by(
                catalog_type="company", slug="intermex").first()
            assert row is not None
            assert row.mime_type == "image/png"
            assert row.file_size > 0
            # Parent row's logo_url mirrors the public URL.
            cat = TVCompanyCatalog.query.filter_by(slug="intermex").first()
            assert "/tv/logo/company/intermex" in cat.logo_url
    finally:
        _cleanup(path)


def test_seed_disk_handles_svg(client):
    """SVG is the preferred format — a tiny dummy SVG should import
    with the right mime."""
    path = _drop_logo("company", "maxi", "svg",
                      b'<svg xmlns="http://www.w3.org/2000/svg"></svg>')
    try:
        with flask_app.app_context():
            _seed_tv_logos_from_disk()
        with client.application.app_context():
            row = TVCatalogLogo.query.filter_by(
                catalog_type="company", slug="maxi").first()
            assert row is not None
            assert row.mime_type == "image/svg+xml"
    finally:
        _cleanup(path)


def test_seed_disk_skips_unknown_slug(client):
    """A file whose slug doesn't match any catalog row is silently
    skipped (no crash, no row written) — operators may drop logos
    for upcoming entries before adding the catalog rows."""
    path = _drop_logo("company", "totally-fake-brand-9999", "png",
                      b"\x89PNG\r\n\x1a\n")
    try:
        with flask_app.app_context():
            _seed_tv_logos_from_disk()
        with client.application.app_context():
            row = TVCatalogLogo.query.filter_by(
                slug="totally-fake-brand-9999").first()
            assert row is None
    finally:
        _cleanup(path)


def test_seed_disk_does_not_override_existing_logo(client):
    """A previously-uploaded UI logo wins — the disk seed never
    overrides operator-managed state."""
    # Pre-existing logo in the table.
    with client.application.app_context():
        db.session.add(TVCatalogLogo(
            catalog_type="company", slug="vigo",
            mime_type="image/png",
            blob=b"old-blob-bytes",
            file_size=14,
        ))
        db.session.commit()
    path = _drop_logo("company", "vigo", "png",
                      b"new-blob-from-disk")
    try:
        with flask_app.app_context():
            _seed_tv_logos_from_disk()
        with client.application.app_context():
            row = TVCatalogLogo.query.filter_by(slug="vigo").first()
            # Old blob preserved — disk file ignored.
            assert row.blob == b"old-blob-bytes"
    finally:
        _cleanup(path)


def test_seed_disk_skips_oversized_file(client):
    """Same 200 KiB cap as the upload endpoint — files over the
    limit are silently skipped."""
    path = _drop_logo("company", "ria", "png",
                      b"x" * (250 * 1024))  # 250 KiB
    try:
        with flask_app.app_context():
            _seed_tv_logos_from_disk()
        with client.application.app_context():
            row = TVCatalogLogo.query.filter_by(slug="ria").first()
            assert row is None
    finally:
        _cleanup(path)


def test_seed_disk_skips_unknown_extension(client):
    """File with an extension not in the whitelist is skipped."""
    path = _drop_logo("company", "ria", "bin", b"random-bytes")
    try:
        with flask_app.app_context():
            _seed_tv_logos_from_disk()
        with client.application.app_context():
            row = TVCatalogLogo.query.filter_by(slug="ria").first()
            assert row is None
    finally:
        _cleanup(path)


def test_seed_disk_is_idempotent(client):
    """Re-running with the same files in place makes no new
    inserts and doesn't crash."""
    path = _drop_logo("company", "moneygram", "png",
                      b"\x89PNG\r\n\x1a\nbody")
    try:
        with flask_app.app_context():
            first = _seed_tv_logos_from_disk()
            second = _seed_tv_logos_from_disk()
        assert first == 1
        assert second == 0
    finally:
        _cleanup(path)


def test_seed_disk_handles_missing_directory(client):
    """If static/seed-logos/companies/ doesn't exist (fresh repo
    clone), the loader returns 0 without crashing."""
    # Temporarily move the directory out of the way.
    sub = os.path.join(_seed_dir(), "companies")
    backup = sub + ".test-backup"
    moved = False
    if os.path.isdir(sub):
        os.rename(sub, backup)
        moved = True
    try:
        # Should be a no-op, not an exception.
        n = _seed_tv_logos_from_disk()
        assert isinstance(n, int)
    finally:
        if moved:
            os.rename(backup, sub)
