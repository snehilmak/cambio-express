"""PosImport — price-book warm start (P2-3).

The register journal already carries everything a starter price
book needs: every ItemLine has the scan code (UPC digits or keyed
PLU), the description, the site's merchandise code, and the shelf
price at the time of sale. This module harvests the distinct items
out of the store's staged journal files and seeds the Catalog
module's price book from them — the "your price book built itself"
moment vs. keying hundreds of items by hand.

Rules:
* Newest sale wins — description + price come from the latest
  business date an item was seen (price changes track forward).
* Fuel lines and code-less items are skipped (fuel is not a shelf
  item; a missing POSCode can't be looked up later).
* Departments map through the operator's existing PosMerchandiseMap
  (merchandise code → Department) — unmapped codes seed with no
  department, never a guess.
* Seeding NEVER overwrites: scan codes already in the price book
  are skipped, so operator edits always survive a re-seed.

Harvest re-parses the staged originals (same posture as day
commits — parser fixes re-harvest history). A month of journals is
~17k files and parses in a few seconds; fine for an occasional
operator-triggered call, revisit if it ever runs on a hot path.
"""
from __future__ import annotations

import gzip
from dataclasses import dataclass
from datetime import date

from sqlalchemy.orm import Session

from api.Modules.Catalog.Models import PriceBookItem
from api.Modules.Catalog.Services import create_item
from api.Modules.DayClose.Models import Department
from api.Modules.PosImport.Models import PosJournalFile, PosMerchandiseMap
from api.Modules.PosImport.Services.naxml import (
    PosJournalParseError,
    parse_pjr,
)

SEED_SOURCE = "gilbarco"


@dataclass
class HarvestedItem:
    pos_code: str
    pos_code_format: str
    description: str
    merchandise_code: str
    department_id: int | None
    department_name: str
    price_cents: int
    last_seen: date
    seen_count: int
    already_in_price_book: bool


def harvest_price_book(
    db: Session, store_id: int,
) -> list[HarvestedItem]:
    """Distinct sellable items across the store's staged journal
    files, newest-sale-wins, sorted by description."""
    files = (
        db.query(PosJournalFile)
        .filter(
            PosJournalFile.store_id == store_id,
            PosJournalFile.parse_error == "",
            PosJournalFile.business_date.isnot(None),
        )
        .all()
    )
    by_code: dict[str, HarvestedItem] = {}
    for f in files:
        try:
            event = parse_pjr(gzip.decompress(f.content_gz))
        except (PosJournalParseError, OSError):
            continue
        if event.business_date is None:
            continue
        for item in event.items:
            code = item.pos_code.strip()
            if item.is_fuel or not code:
                continue
            seen = by_code.get(code)
            if seen is None:
                by_code[code] = HarvestedItem(
                    pos_code=code,
                    pos_code_format=(
                        item.pos_code_format
                        if item.pos_code_format in ("upc", "plu") else "upc"
                    ),
                    description=item.description,
                    merchandise_code=item.merchandise_code,
                    department_id=None,
                    department_name="",
                    price_cents=item.regular_price_cents,
                    last_seen=event.business_date,
                    seen_count=1,
                    already_in_price_book=False,
                )
                continue
            seen.seen_count += 1
            if event.business_date >= seen.last_seen:
                seen.last_seen = event.business_date
                if item.description:
                    seen.description = item.description
                if item.regular_price_cents:
                    seen.price_cents = item.regular_price_cents
                if item.merchandise_code:
                    seen.merchandise_code = item.merchandise_code

    if not by_code:
        return []

    # Merchandise code → operator department (only mapped codes).
    dept_by_code: dict[str, tuple[int, str]] = {
        m.merchandise_code: (int(m.department_id), m.department.name or "")
        for m in (
            db.query(PosMerchandiseMap)
            .join(Department, Department.id == PosMerchandiseMap.department_id)
            .filter(PosMerchandiseMap.store_id == store_id)
            .all()
        )
    }
    existing_codes = {
        code for (code,) in
        db.query(PriceBookItem.pos_code)
          .filter_by(store_id=store_id)
          .all()
    }
    for h in by_code.values():
        mapped = dept_by_code.get(h.merchandise_code)
        if mapped is not None:
            h.department_id, h.department_name = mapped
        h.already_in_price_book = h.pos_code in existing_codes

    return sorted(
        by_code.values(),
        key=lambda h: (h.description.lower(), h.pos_code),
    )


@dataclass
class SeedResult:
    created: int
    skipped_existing: int


def seed_price_book(
    db: Session, store_id: int,
) -> SeedResult:
    """Create price-book items for every harvested item whose scan
    code isn't already in the catalog. Idempotent — a second run
    creates nothing new. Items land with source="gilbarco" and stay
    fully editable like any manual entry."""
    created = 0
    skipped = 0
    for h in harvest_price_book(db, store_id):
        if h.already_in_price_book:
            skipped += 1
            continue
        create_item(
            db, store_id,
            {
                "pos_code": h.pos_code,
                "pos_code_format": h.pos_code_format,
                "name": h.description or f"Item {h.pos_code}",
                "department_id": h.department_id,
                "price": h.price_cents / 100.0,
            },
            source=SEED_SOURCE,
        )
        created += 1
    return SeedResult(created=created, skipped_existing=skipped)


__all__ = [
    "HarvestedItem", "SEED_SOURCE", "SeedResult",
    "harvest_price_book", "seed_price_book",
]
