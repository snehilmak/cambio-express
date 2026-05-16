"""Build the context dict the public TV rate-board template renders.

Pure — no request-context dependency — so the helper can be
exercised directly by unit tests. Logo URLs are hand-built as
``/tv/logo/<type>/<slug>`` (the canonical public URL the TV
client fetches) instead of going through a routing helper.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session


def _csv_split(s: str | None) -> list[str]:
    return [x.strip() for x in (s or "").split(",") if x.strip()]


def _logo_url(catalog_type: str, slug: str, version: int) -> str:
    """The public URL the TV client fetches logos from.

    Cache-bust by appending ``?v=<updated_at_unix>``. Templates
    used to call ``url_for("tv.tv_catalog_logo", …)`` to build
    this; we hardcode it here so the helper stays Flask-free.
    """
    base = f"/tv/logo/{catalog_type}/{slug}"
    return f"{base}?v={version}" if version else base


def build_tv_board_context(display, store, session: Session) -> dict[str, Any]:
    """Return the context dict ``tv_display_public.html`` needs.

    Resolves catalog slugs to display_name so the public board shows
    "BBVA Bancomer" not "mx_bbva_bancomer". Lookups include INACTIVE
    catalog rows so legacy references keep rendering even after the
    superadmin retires a catalog entry.

    ``session`` is a plain SQLAlchemy session. Caller is responsible
    for the session lifecycle — this helper never commits.
    """
    # Lazy-import the Models so this module stays cheap to import
    # (tests that don't render the board don't pay the SQLAlchemy
    # class-build cost just to type-check this signature).
    from api.Modules.TVDisplay.Models import (
        TVBankCatalog, TVCatalogLogo, TVCompanyCatalog,
        TVDisplayCountry, TVDisplayPayoutBank, TVDisplayRate,
    )

    s = session

    # Resolve all catalog slugs in one query rather than per-section.
    company_name_by_slug = {c.slug: c.display_name
                             for c in s.query(TVCompanyCatalog).all()}
    bank_name_by_slug = {b.slug: b.display_name
                          for b in s.query(TVBankCatalog).all()}
    # Logo URL maps with cache-bust suffix. Only includes catalog
    # rows whose ``logo_url`` is populated; entries without uploads
    # are absent and the template falls back to ``display_name``
    # text.
    logo_versions = {(r.catalog_type, r.slug): int(r.updated_at.timestamp())
                      for r in s.query(TVCatalogLogo).all()}
    company_logo_by_slug: dict[str, str] = {}
    for c in s.query(TVCompanyCatalog).all():
        if c.logo_url:
            v = logo_versions.get(("company", c.slug), 0)
            company_logo_by_slug[c.slug] = _logo_url("company", c.slug, v)
    bank_logo_by_slug: dict[str, str] = {}
    for b in s.query(TVBankCatalog).all():
        if b.logo_url:
            v = logo_versions.get(("bank", b.slug), 0)
            bank_logo_by_slug[b.slug] = _logo_url("bank", b.slug, v)

    countries = (s.query(TVDisplayCountry)
                  .filter_by(display_id=display.id)
                  .order_by(TVDisplayCountry.sort_order, TVDisplayCountry.id)
                  .all())
    sections: list[dict[str, Any]] = []
    seen: set[str] = set()
    global_companies: list[str] = []
    for c in countries:
        for slug in _csv_split(c.mt_companies):
            if slug not in seen:
                seen.add(slug)
                global_companies.append(slug)
    global_company_labels = [company_name_by_slug.get(x, x) for x in global_companies]
    global_company_logos  = [company_logo_by_slug.get(x, "") for x in global_companies]

    for c in countries:
        banks = (s.query(TVDisplayPayoutBank)
                  .filter_by(country_id=c.id)
                  .order_by(TVDisplayPayoutBank.sort_order,
                            TVDisplayPayoutBank.id).all())
        rate_map: dict[tuple[int, str], float] = {}
        if banks:
            for r in (s.query(TVDisplayRate)
                       .filter(TVDisplayRate.bank_id.in_([b.id for b in banks]))
                       .all()):
                rate_map[(r.bank_id, r.mt_company)] = r.rate
        sections.append({
            "country": c,
            "banks":   banks,
            "rates":   rate_map,
        })

    return {
        "display":               display,
        "store":                 store,
        "sections":              sections,
        "global_companies":      global_companies,
        "global_company_labels": global_company_labels,
        "global_company_logos":  global_company_logos,
        "bank_name_by_slug":     bank_name_by_slug,
        "bank_logo_by_slug":     bank_logo_by_slug,
    }
