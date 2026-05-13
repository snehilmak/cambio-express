"""TVDisplay — Models.

The public TV-display board ("Cheapest Money Transfer" rate board)
plus the companion Fire TV / Google TV pairing flow. Nine SQLAlchemy
classes:

* ``TVDisplay``           — one row per store that owns the
                            ``tv_display`` add-on.
* ``TVDisplayCountry``    — one section on the board (Mexico,
                            Guatemala, …).
* ``TVDisplayPayoutBank`` — one bank row in a country's matrix.
* ``TVDisplayRate``       — the cell value at (bank, mt_company).
* ``TVPairing``           — one row per paired companion-app device.
* ``TVPendingPair``       — pending pair attempt (Fire TV asks for
                            a code, waits for an admin claim).
* ``TVCompanyCatalog``    — curated MT-company picker (Intermex,
                            Maxi, Barri, …).
* ``TVBankCatalog``       — curated payout-bank picker.
* ``TVCatalogLogo``       — logo BLOB for a catalog entry.

These used to live in ``app.py`` as ``class Foo(db.Model)``; first
slice of the Final-phase model-extraction work. ``app.py`` now
re-exports the names so every ``from app import TVDisplay`` keeps
working unchanged.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean, Column, DateTime, Float, ForeignKey, Integer, LargeBinary,
    String, UniqueConstraint,
)

from api.Core.Database import Base


class TVDisplay(Base):
    """One row per store that owns the tv_display add-on. Created
    lazily on first visit to /admin/tv-display."""

    __tablename__ = "tv_display"
    id              = Column(Integer, primary_key=True)
    store_id        = Column(Integer, ForeignKey("store.id"),
                              unique=True, nullable=False)
    # 32-char URL-safe random token. Anyone with the URL can view —
    # rotation is a one-click action on the admin page.
    public_token    = Column(String(48), unique=True, nullable=False)
    # Bilingual title bar. Defaults match the screenshot the pilot
    # store provided ("Cheapest Money Transfer / Mejor Tipo de Cambio").
    title           = Column(String(120), default="Cheapest Money Transfer")
    subtitle        = Column(String(120), default="Mejor Tipo de Cambio")
    # Display orientation: "landscape" / "portrait" / "auto" (auto =
    # respect the device's screen orientation). The TV-side CSS
    # adapts via media queries; this is the explicit override.
    orientation     = Column(String(16), default="auto")
    # Light / dark theme override for the BOARD. Independent of
    # admin theme_preference (the operator likes dark mode in their
    # office, the TV needs the high-contrast light board).
    theme           = Column(String(16), default="light")
    last_updated_at = Column(DateTime, default=datetime.utcnow)
    created_at      = Column(DateTime, default=datetime.utcnow)
    # DEPRECATED — left in the schema only because CLAUDE.md
    # forbids dropping columns from a running DB. The pair-code
    # state lives in TVPendingPair now (TV-initiated flow). These
    # columns can be backfill-renamed in a follow-up deploy.
    pair_code             = Column(String(8), default="")
    pair_code_expires_at  = Column(DateTime, nullable=True)


class TVDisplayCountry(Base):
    """One section on the board (Mexico, Guatemala, …)."""

    __tablename__ = "tv_display_country"
    id            = Column(Integer, primary_key=True)
    display_id    = Column(Integer, ForeignKey("tv_display.id"),
                            nullable=False, index=True)
    country_code  = Column(String(4), default="")  # ISO-2 — drives the flag emoji
    country_name  = Column(String(80), nullable=False)
    sort_order    = Column(Integer, default=0)
    # CSV of MT-company column headers shown for this country. Order
    # matters (defines column order). Example: "Maxi,Cibao,Vigo".
    mt_companies  = Column(String(500), default="")


class TVDisplayPayoutBank(Base):
    """One row in a country's matrix — "Bancomer", "Banorte", etc."""

    __tablename__ = "tv_display_payout_bank"
    id          = Column(Integer, primary_key=True)
    country_id  = Column(Integer, ForeignKey("tv_display_country.id"),
                          nullable=False, index=True)
    bank_name   = Column(String(120), nullable=False)
    sort_order  = Column(Integer, default=0)


class TVDisplayRate(Base):
    """The cell value at (bank, mt_company). Sparse — a cell with no
    rate set is rendered as "—" on the board."""

    __tablename__ = "tv_display_rate"
    id          = Column(Integer, primary_key=True)
    bank_id     = Column(Integer, ForeignKey("tv_display_payout_bank.id"),
                          nullable=False, index=True)
    # The MT company column header — must match one of the strings
    # in the parent country's mt_companies CSV. Not FK'd because the
    # column list is a free-form list per country, not a global table.
    mt_company  = Column(String(80), nullable=False)
    rate        = Column(Float, nullable=False)
    updated_at  = Column(DateTime, default=datetime.utcnow,
                          onupdate=datetime.utcnow)
    __table_args__ = (
        UniqueConstraint("bank_id", "mt_company",
                          name="uq_tvrate_bank_company"),
    )


class TVPairing(Base):
    """One row per paired companion-app device (Fire TV, Google TV).
    The redeem endpoint mints a device_token here and returns the
    per-device URL /tv/device/<device_token> — never the shared
    public_token, so the Fire TV app can't sideload its credential
    into other devices.

    Single-active-pairing per display: a fresh redeem revokes any
    prior unrevoked TVPairing for the same display. That enforces
    'one $5 subscription = one Fire TV at a time' without affecting
    legacy /tv/<public_token> tablet/Chromecast users.
    """

    __tablename__ = "tv_pairing"
    id            = Column(Integer, primary_key=True)
    display_id    = Column(Integer, ForeignKey("tv_display.id"),
                            nullable=False, index=True)
    # 32-byte URL-safe random; same generator as public_token.
    device_token  = Column(String(48), unique=True, nullable=False)
    # Free-form label the app may submit ("Fire TV — Counter 1").
    # Empty string until the operator names it from the admin UI.
    device_label  = Column(String(80), default="")
    paired_at     = Column(DateTime, default=datetime.utcnow)
    # Bumped on every successful /tv/device/<token> render so the
    # admin UI can show "last seen 2 min ago".
    last_seen_at  = Column(DateTime, default=datetime.utcnow)
    # Set when superseded by a new pairing or manually revoked. A row
    # with revoked_at IS NOT NULL serves 404 on its device URL.
    revoked_at    = Column(DateTime, nullable=True)


class TVPendingPair(Base):
    """Pending pair attempt — created when a Fire TV opens the app
    and asks for a code. Lives in this table until either:
      (a) An admin claims the code from /tv-display → we revoke any
          prior active TVPairing on their display and create a fresh
          TVPairing tied to this row's device_token. The Fire TV's
          poll then transitions to "claimed" and starts loading the
          rate board. claimed_at + claimed_pairing_id are set.
      (b) The 10-minute window elapses → /api/tv-pair/status returns
          "expired" and the Fire TV app calls /init for a new code.

    Why a separate table from TVPairing:
      - Pending rows don't yet have a display_id (the operator
        hasn't entered their account yet to claim the code).
        Keeping TVPairing.display_id NOT NULL avoids loose semantics
        and lets the existing render path stay simple.
      - The device_token in this row is REUSED on claim — copied
        into the new TVPairing — so the Fire TV app stores its
        token once at /init time and never sees a rotation.

    Single-claim is enforced by claimed_at + claimed_pairing_id +
    a uniqueness check at claim time; no two pending rows can
    redeem to a TVPairing.
    """

    __tablename__ = "tv_pending_pair"
    id            = Column(Integer, primary_key=True)
    # 6-char alphanumeric (same alphabet as PAIR_CODE_ALPHABET).
    # Indexed because /api/tv-pair/status does the lookup by code
    # via a join, and so does /tv-display/claim.
    code          = Column(String(8), unique=True, nullable=False, index=True)
    # Stable from /init through claim. The Fire TV stores this and
    # never receives a different one.
    device_token  = Column(String(48), unique=True, nullable=False, index=True)
    # Free-form label the app may submit ("Fire TV — Stick 4K Max"),
    # carried over to TVPairing.device_label on claim.
    device_label  = Column(String(80), default="")
    created_at    = Column(DateTime, default=datetime.utcnow)
    expires_at    = Column(DateTime, nullable=False)
    # Set on successful admin claim. Once set, this row is "spent"
    # and the Fire TV polls find the resulting TVPairing instead.
    claimed_at         = Column(DateTime, nullable=True)
    claimed_pairing_id = Column(Integer,
                                 ForeignKey("tv_pairing.id"),
                                 nullable=True)


class TVCompanyCatalog(Base):
    """Curated MT companies (Intermex, Maxi, Barri, etc.) selectable
    from the column-header picker on the TV display country editor.

    Why a global catalog instead of free-text per store:
      - Two stores both type "Maxi" / "MaxiTransfer" / "Maxi Money"
        otherwise; cross-store fraud detection and chain-wide
        consistency need a canonical name.
      - Eventually each row carries a logo_url (Phase 2). Decoupling
        the slug (immutable identifier) from display_name (mutable
        label) means we can rename / re-logo without breaking
        existing references on TVDisplayCountry.mt_companies.

    is_active=False hides the entry from the picker without losing
    references — older country sections still resolve the slug to
    display_name for rendering.
    """

    __tablename__ = "tv_company_catalog"
    id           = Column(Integer, primary_key=True)
    # URL-safe lowercase identifier (e.g. "maxi", "intermex"). The
    # column header CSV on TVDisplayCountry.mt_companies stores
    # these slugs. Immutable after creation.
    slug         = Column(String(40), unique=True, nullable=False, index=True)
    # Human-friendly label rendered on the public board. Editable.
    display_name = Column(String(80), nullable=False)
    # Future: nominative-use logo (Phase 2 of the catalog rollout).
    # Defaults to empty so Phase 1 ships without legal/asset
    # acquisition blocking the picker UI.
    logo_url     = Column(String(255), default="")
    sort_order   = Column(Integer, default=0)
    is_active    = Column(Boolean, default=True)
    created_at   = Column(DateTime, default=datetime.utcnow)


class TVBankCatalog(Base):
    """Curated payout banks (BBVA Bancomer, Banco Industrial, etc.)
    selectable from the row-name picker on the country editor. Same
    slug + display_name pattern as TVCompanyCatalog, plus a
    country_code so the editor's bank picker can scope to "banks
    for Mexico" vs "banks for Guatemala."
    """

    __tablename__ = "tv_bank_catalog"
    id           = Column(Integer, primary_key=True)
    slug         = Column(String(60), unique=True, nullable=False, index=True)
    display_name = Column(String(80), nullable=False)
    # ISO-2; country_code IS NOT a FK to anything (countries are
    # picked from a flat list). Indexed because the picker filters
    # by it on every editor render.
    country_code = Column(String(4), default="", index=True)
    logo_url     = Column(String(255), default="")
    sort_order   = Column(Integer, default=0)
    is_active    = Column(Boolean, default=True)
    created_at   = Column(DateTime, default=datetime.utcnow)


class TVCatalogLogo(Base):
    """Logo image bytes for a catalog entry. Stored as a BLOB so the
    feature works on every deploy target (Render free tier wipes the
    filesystem on every redeploy; a persistent disk works but adds
    infra config we'd rather avoid).

    Lookup is by (catalog_type, slug) — single shared table for both
    TVCompanyCatalog and TVBankCatalog. Discriminator is "company" or
    "bank"; slug matches the parent catalog row.

    Served via GET /tv/logo/<type>/<slug> with a year-long
    Cache-Control. Templates bust the cache by appending
    ?v=<updated_at_unix> when they emit the URL — re-uploads
    invalidate downstream caches without an HTTP-level mechanism.

    Size + total bytes
    - Per file: capped at 200 KiB on upload (validated server-side).
    - Worst case: 46 catalog rows × 200 KB ≈ 9 MB. Negligible for
      Postgres; the BLOB column on SQLite handles it just as well.
    """

    __tablename__ = "tv_catalog_logo"
    id           = Column(Integer, primary_key=True)
    # "company" | "bank" — keep the values short, the URL embeds them.
    catalog_type = Column(String(8), nullable=False, index=True)
    # Matches TVCompanyCatalog.slug or TVBankCatalog.slug — NOT a
    # foreign key, since both parent tables have their own slug
    # constraints and we want the logo row to outlive a soft-delete.
    slug         = Column(String(60), nullable=False, index=True)
    # Whitelisted by the upload endpoint: image/png | image/jpeg |
    # image/webp | image/svg+xml. SVG is allowed because it's the
    # ideal asset for the public TV board (scales to any density).
    mime_type    = Column(String(40), nullable=False)
    blob         = Column(LargeBinary, nullable=False)
    file_size    = Column(Integer, default=0)
    updated_at   = Column(DateTime, default=datetime.utcnow,
                           onupdate=datetime.utcnow)
    __table_args__ = (
        UniqueConstraint("catalog_type", "slug",
                          name="uq_tv_catalog_logo_type_slug"),
    )


__all__ = [
    "TVDisplay",
    "TVDisplayCountry",
    "TVDisplayPayoutBank",
    "TVDisplayRate",
    "TVPairing",
    "TVPendingPair",
    "TVCompanyCatalog",
    "TVBankCatalog",
    "TVCatalogLogo",
]
