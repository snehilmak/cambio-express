"""TV Display catalog seed.

Curated defaults for the country picker, MT-company column picker,
and payout-bank row picker on the TV-display editor — plus
idempotent boot-time seeding so a fresh install ships with usable
data instead of an empty board.

Public entry point:

  - :func:`run(session, repo_root)` — call from ``init_db`` (or the
    standalone scripts) to seed catalogs + import drop-in logos +
    backfill legacy rows. Idempotent; safe on every boot.

All data tables (``_DEFAULT_TV_COMPANIES``, ``_DEFAULT_TV_BANKS``,
``_TV_COUNTRY_PICKER``) and helpers (``normalize_logo_blob``,
``LOGO_MAX_BYTES``, etc.) used to live in ``app.py``; extracted in
the Step 8 cleanup so the boot module stays slim.
"""
from __future__ import annotations

import io
import os
from datetime import datetime

from sqlalchemy import or_
from sqlalchemy.orm import Session
from api.Core.Clock import utc_now


# Curated default lists for the TV-display country editor's
# company-column picker and bank-row picker. Idempotent — only
# inserts entries whose slug doesn't already exist, so the
# superadmin can edit / disable / re-sort without the next boot
# clobbering their changes.
#
# Slugs are URL-safe lowercase identifiers; display_name is what
# operators see in the picker and on the public board. ``logo_url``
# stays empty here (Phase 1 ships text-only; Phase 2 wires up the
# upload flow).
DEFAULT_TV_COMPANIES: list[tuple[str, str, int]] = [
    # (slug, display_name, sort_order)
    ("intermex",       "Intermex",         10),
    ("maxi",           "Maxi",             20),
    ("barri",          "Barri",            30),
    ("vigo",           "Vigo",             40),
    ("ria",            "RIA",              50),
    ("moneygram",      "MoneyGram",        60),
    ("western_union",  "Western Union",    70),
    ("cibao",          "Cibao Express",    80),
    ("sigue",          "Sigue",            90),
    ("dolex",          "Dolex",           100),
    ("boss_revolution","Boss Revolution", 110),
    ("xoom",           "Xoom",            120),
]

# Banks scoped per country. Country codes are ISO-2 uppercase.
# Each tuple is (slug, display_name, country_code, sort_order).
DEFAULT_TV_BANKS: list[tuple[str, str, str, int]] = [
    # ── Mexico ───────────────────────────────────────────────
    ("mx_bbva_bancomer", "BBVA Bancomer",    "MX", 10),
    ("mx_banorte",       "Banorte",          "MX", 20),
    ("mx_santander",     "Santander México", "MX", 30),
    ("mx_banamex",       "Citibanamex",      "MX", 40),
    ("mx_hsbc",          "HSBC México",      "MX", 50),
    ("mx_scotiabank",    "Scotiabank",       "MX", 60),
    ("mx_bancoppel",     "Bancoppel",        "MX", 70),
    ("mx_banco_azteca",  "Banco Azteca",     "MX", 80),
    ("mx_inbursa",       "Inbursa",          "MX", 90),
    ("mx_elektra",       "Elektra",          "MX",100),
    ("mx_walmart",       "Walmart",          "MX",110),
    ("mx_soriana",       "Soriana",          "MX",120),

    # ── Guatemala ────────────────────────────────────────────
    ("gt_industrial",    "Banco Industrial", "GT", 10),
    ("gt_banrural",      "Banrural",         "GT", 20),
    ("gt_bac",           "BAC Credomatic",   "GT", 30),
    ("gt_gtcontinental", "G&T Continental",  "GT", 40),
    ("gt_bantrab",       "Bantrab",          "GT", 50),
    ("gt_vivibanco",     "Vivibanco",        "GT", 60),

    # ── Honduras ─────────────────────────────────────────────
    ("hn_atlantida",     "Banco Atlántida",  "HN", 10),
    ("hn_banpais",       "Banpais",          "HN", 20),
    ("hn_ficohsa",       "Ficohsa",          "HN", 30),
    ("hn_bac",           "BAC Credomatic",   "HN", 40),
    ("hn_occidente",     "Banco de Occidente","HN",50),
    ("hn_azteca",        "Banco Azteca",     "HN", 60),

    # ── El Salvador ──────────────────────────────────────────
    ("sv_agricola",      "Banco Agrícola",   "SV", 10),
    ("sv_cuscatlan",     "Banco Cuscatlán",  "SV", 20),
    ("sv_davivienda",    "Davivienda",       "SV", 30),
    ("sv_bac",           "BAC Credomatic",   "SV", 40),
    ("sv_hipotecario",   "Banco Hipotecario","SV", 50),

    # ── Dominican Republic ───────────────────────────────────
    ("do_banreservas",   "Banreservas",          "DO", 10),
    ("do_popular",       "Banco Popular Dominicano","DO", 20),
    ("do_bhd",           "BHD León",             "DO", 30),
    ("do_santa_cruz",    "Banco Santa Cruz",     "DO", 40),
    ("do_cibao",         "Asociación Cibao",     "DO", 50),
]

# Curated country list for the TV-display country picker. Order is
# intentional, not alphabetical: the heaviest US→LATAM corridors
# appear first so the typical operator picks from the top of the
# list.
TV_COUNTRY_PICKER: list[tuple[str, str]] = [
    ("MX", "Mexico"),
    ("GT", "Guatemala"),
    ("HN", "Honduras"),
    ("SV", "El Salvador"),
    ("DO", "Dominican Republic"),
    ("NI", "Nicaragua"),
    ("CR", "Costa Rica"),
    ("PA", "Panama"),
    ("CO", "Colombia"),
    ("EC", "Ecuador"),
    ("PE", "Peru"),
    ("VE", "Venezuela"),
    ("CU", "Cuba"),
    ("HT", "Haiti"),
    ("JM", "Jamaica"),
    ("BR", "Brazil"),
    ("AR", "Argentina"),
    ("CL", "Chile"),
    ("BO", "Bolivia"),
    ("PY", "Paraguay"),
    ("UY", "Uruguay"),
    ("PH", "Philippines"),
    ("IN", "India"),
    ("PK", "Pakistan"),
    ("BD", "Bangladesh"),
    ("VN", "Vietnam"),
    ("NG", "Nigeria"),
    ("GH", "Ghana"),
    ("KE", "Kenya"),
    ("ET", "Ethiopia"),
]


# Logo blob normalization — the upload + drop-in import paths share
# this so every catalog entry renders at the same visual weight on
# the public board.
LOGO_MAX_BYTES = 200 * 1024

# Standard canvas every raster logo is fit-and-padded into. 600x200
# is high-enough resolution for 4K TV display + 3x retina laptops
# without cropping the brand mark; 3:1 ratio fits both wordmarks
# (e.g. "Western Union" wide) and abbreviation marks (e.g. "BBVA"
# squarish) without one looking dwarfed against the other.
_LOGO_CANVAS_WIDTH  = 600
_LOGO_CANVAS_HEIGHT = 200


def normalize_logo_blob(blob: bytes, mime: str) -> tuple[bytes, str]:
    """Standardize an uploaded logo so every catalog entry renders
    at the same visual weight on the public TV board.

    Raster (PNG/JPEG/WebP):
      - Open with Pillow, scale (preserving aspect) to fit a
        600x200 canvas via thumbnail + LANCZOS resampling.
      - Center on a transparent canvas (RGBA).
      - Save as optimized PNG. JPEG inputs that have no alpha
        come out as PNG with a transparent surrounding area.
      - Bytes-on-wire are uniform regardless of the source's
        pixel dimensions.

    SVG:
      - Pass through unchanged. The viewBox is the logical canvas;
        CSS object-fit:contain handles display scaling without
        quality loss.

    Falls back to (blob, mime) unchanged on any Pillow error so a
    malformed-but-acceptable upload still lands in the DB rather
    than blocking the operator with an opaque error.

    Returns (normalized_blob, normalized_mime). Raster always
    becomes "image/png"; SVG stays "image/svg+xml".
    """
    if mime == "image/svg+xml":
        return blob, mime

    try:
        from PIL import Image
    except ImportError:
        # Pillow not installed (dev shell, never in prod requirements).
        return blob, mime

    try:
        with Image.open(io.BytesIO(blob)) as src:
            src.load()  # force-decode now so a corrupt image fails fast
            scaled = src.copy()
            scaled.thumbnail(
                (_LOGO_CANVAS_WIDTH, _LOGO_CANVAS_HEIGHT),
                Image.Resampling.LANCZOS,
            )
            if scaled.mode != "RGBA":
                scaled = scaled.convert("RGBA")

            canvas = Image.new(
                "RGBA",
                (_LOGO_CANVAS_WIDTH, _LOGO_CANVAS_HEIGHT),
                (0, 0, 0, 0),
            )
            x = (_LOGO_CANVAS_WIDTH  - scaled.width)  // 2
            y = (_LOGO_CANVAS_HEIGHT - scaled.height) // 2
            canvas.paste(scaled, (x, y), scaled)

            out = io.BytesIO()
            canvas.save(out, format="PNG", optimize=True)
            return out.getvalue(), "image/png"
    except Exception:
        # Corrupt image / unsupported format / Pillow stack issue —
        # store the original bytes rather than blocking the upload.
        # The serve route still validates mime against the whitelist.
        return blob, mime


def seed_catalogs(session: Session) -> None:
    """Pre-load the curated MT-company + bank pickers. Idempotent —
    re-running only inserts entries with new slugs, so superadmin
    edits are preserved across deploys."""
    from api.Modules.TVDisplay.Models import TVBankCatalog, TVCompanyCatalog

    for slug, display_name, sort_order in DEFAULT_TV_COMPANIES:
        if not session.query(TVCompanyCatalog).filter_by(slug=slug).first():
            session.add(TVCompanyCatalog(
                slug=slug, display_name=display_name,
                sort_order=sort_order, is_active=True,
            ))
    for slug, display_name, country_code, sort_order in DEFAULT_TV_BANKS:
        if not session.query(TVBankCatalog).filter_by(slug=slug).first():
            session.add(TVBankCatalog(
                slug=slug, display_name=display_name,
                country_code=country_code,
                sort_order=sort_order, is_active=True,
            ))
    session.commit()


def seed_logos_from_disk(session: Session, repo_root: str) -> int:
    """One-shot importer: scan ``static/seed-logos/{companies,banks}/``
    for files named ``<slug>.{svg,png,jpg,jpeg,webp}`` and import any
    that aren't already in ``TVCatalogLogo``. Idempotent — re-running
    only inserts new entries; existing logos (uploaded via the
    superadmin UI or a previous boot) are left alone.

    The intent: drop logo files into a directory, redeploy, and they
    auto-load. Lets a designer / contractor populate the catalog by
    file-drop without clicking through the upload UI 46 times.
    Operators can still upload + replace via the UI; that path takes
    precedence (we only import when no logo row exists for the slug)."""
    from api.Modules.TVDisplay.Models import (
        TVBankCatalog, TVCatalogLogo, TVCompanyCatalog,
    )

    seed_dir = os.path.join(repo_root, "static", "seed-logos")
    if not os.path.isdir(seed_dir):
        return 0

    # MIME type by file extension.
    ext_to_mime = {
        ".svg":  "image/svg+xml",
        ".png":  "image/png",
        ".jpg":  "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
    }

    imported = 0
    # "company" → "companies" is irregular; spell out plurals.
    type_to_dir = {"company": "companies", "bank": "banks"}
    for catalog_type, sub_name in type_to_dir.items():
        sub = os.path.join(seed_dir, sub_name)
        if not os.path.isdir(sub):
            continue
        for filename in os.listdir(sub):
            path = os.path.join(sub, filename)
            if not os.path.isfile(path):
                continue
            slug, ext = os.path.splitext(filename)
            slug = slug.strip().lower()
            ext = ext.lower()
            mime = ext_to_mime.get(ext)
            if not mime or not slug:
                continue
            parent_cls = (TVCompanyCatalog if catalog_type == "company"
                           else TVBankCatalog)
            parent = session.query(parent_cls).filter_by(slug=slug).first()
            if parent is None:
                continue
            # Don't override an operator's existing upload.
            if session.query(TVCatalogLogo).filter_by(
                    catalog_type=catalog_type, slug=slug).first() is not None:
                continue
            try:
                with open(path, "rb") as fh:
                    raw_blob = fh.read()
            except OSError:
                continue
            if not raw_blob or len(raw_blob) > LOGO_MAX_BYTES:
                continue
            blob, normalized_mime = normalize_logo_blob(raw_blob, mime)
            session.add(TVCatalogLogo(
                catalog_type=catalog_type, slug=slug,
                mime_type=normalized_mime,
                blob=blob, file_size=len(blob),
                updated_at=utc_now(),
            ))
            # Mirror the public URL into the parent row's logo_url
            # so non-superadmin code can resolve without a logo-table
            # lookup. Hardcoded path because the seed runs outside a
            # Flask request context.
            setattr(parent, "logo_url", f"/tv/logo/{catalog_type}/{slug}")
            imported += 1
    if imported:
        session.commit()
    return imported


def backfill_country_codes(session: Session) -> int:
    """Walk ``TVDisplayCountry``, fill in missing ``country_code`` for
    rows whose ``country_name`` matches an entry in the curated
    picker. Runs on every boot but is a no-op once every row has a
    code (idempotent — only matches rows where country_code is NULL
    or empty).

    Pre-PR-C rows were created via free-text inputs where the
    operator could type the name without an ISO-2. The flag emoji is
    computed from country_code, so those legacy rows render flagless
    on the public board until we backfill."""
    from api.Modules.TVDisplay.Models import TVDisplayCountry

    name_to_iso = {name.lower(): iso for iso, name in TV_COUNTRY_PICKER}
    # Common synonyms / variations the operator might have typed.
    name_to_iso.update({
        "republica dominicana": "DO",
        "dominican republic":   "DO",
        "el salvador":          "SV",
        "costa rica":            "CR",
    })
    fixed = 0
    rows = session.query(TVDisplayCountry).filter(
        or_(TVDisplayCountry.country_code.is_(None),
            TVDisplayCountry.country_code == "")
    ).all()
    for row in rows:
        guess = name_to_iso.get((row.country_name or "").strip().lower())
        if guess:
            setattr(row, "country_code", guess)
            fixed += 1
    if fixed:
        session.commit()
    return fixed


def run(session: Session, repo_root: str) -> int:
    """Seed-on-boot entry point. Returns the count of logos imported
    on this run (the catalog + backfill counts aren't surfaced — they
    log internally and the call sites don't read them).

    Order matters:
      1. ``seed_catalogs`` first — establishes the parent rows that
         the logo importer attaches to.
      2. ``seed_logos_from_disk`` — depends on step 1.
      3. ``backfill_country_codes`` — independent of 1 and 2, but
         cheap so we run it on the same boot path.
    """
    seed_catalogs(session)
    n = seed_logos_from_disk(session, repo_root)
    backfill_country_codes(session)
    return n


__all__ = [
    "DEFAULT_TV_BANKS",
    "DEFAULT_TV_COMPANIES",
    "LOGO_MAX_BYTES",
    "TV_COUNTRY_PICKER",
    "backfill_country_codes",
    "normalize_logo_blob",
    "run",
    "seed_catalogs",
    "seed_logos_from_disk",
]
