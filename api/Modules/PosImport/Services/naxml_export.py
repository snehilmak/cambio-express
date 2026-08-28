"""PosImport — NAXML price-book export (G-4, BETA).

The write-back half of the Gilbarco loop: "edit the price in
DineroBook, the register updates." Generates a Conexxus
NAXML-MaintenanceRequest ItemMaintenance document from the store's
price book, in the shape Gilbarco Passport's Back Office Interface
imports.

BETA until validated against a live Passport site: the NAXML
*journal* shape is ground-truthed from real files, but Passport's
maintenance-import tolerances (required elements, POSCodeFormat
vocabulary, action attributes) need a real site to confirm. The
export is deliberately minimal — item identity, description,
sell price, merchandise code, active flag — because a smaller
document has fewer ways to be rejected. The site agent does NOT
auto-apply this yet; the operator downloads the file and feeds it
through Passport's import (or MWS) until auto-apply is validated.

Pure generation — no DB writes. XML is built with stdlib
ElementTree (output, not parsing — defusedxml guards inputs, not
outputs).
"""
from __future__ import annotations

from datetime import datetime
from xml.etree import ElementTree as ET

from sqlalchemy.orm import Session

from api.Modules.Catalog.Models import PriceBookItem
from api.Modules.PosImport.Models import PosMerchandiseMap

# Our stored pos_code_format → NAXML POSCodeFormat vocabulary.
# Journals from the ground-truth site carry "upcA" for scanned
# 12-digit codes and "plu" for keyed shorts; anything unknown
# exports as upcA (the overwhelmingly common case).
_FORMAT_MAP = {"upc": "upcA", "plu": "plu"}


def _merch_code_by_department(
    db: Session, store_id: int,
) -> dict[int, str]:
    """Reverse of the operator's merchandise-code mapping:
    department_id → one of the site's numeric codes. When several
    codes map to one department, the lowest sorts first (stable
    choice); departments with no code simply export without a
    MerchandiseCode element."""
    out: dict[int, str] = {}
    rows = (
        db.query(PosMerchandiseMap)
        .filter_by(store_id=store_id)
        .order_by(PosMerchandiseMap.merchandise_code)
        .all()
    )
    for m in rows:
        out.setdefault(int(m.department_id), m.merchandise_code)
    return out


def export_items(
    db: Session, store_id: int, *,
    changed_since: datetime | None = None,
    store_location_id: str = "1",
) -> tuple[str, int]:
    """Build the ItemMaintenance XML for the store's active items.
    ``changed_since`` limits to items updated after that moment
    (the "send today's price changes" flow); None exports the full
    book. Returns (xml_string, item_count)."""
    q = (
        db.query(PriceBookItem)
        .filter(
            PriceBookItem.store_id == store_id,
            PriceBookItem.is_active.is_(True),
        )
    )
    if changed_since is not None:
        q = q.filter(PriceBookItem.updated_at >= changed_since)
    items = q.order_by(PriceBookItem.pos_code).all()
    merch_by_dept = _merch_code_by_department(db, store_id)

    root = ET.Element(
        "NAXML-MaintenanceRequest",
        {"version": "3.4", "release": "3.4.1"},
    )
    header = ET.SubElement(root, "TransmissionHeader")
    ET.SubElement(header, "StoreLocationID").text = store_location_id
    ET.SubElement(header, "VendorName").text = "DineroBook"
    ET.SubElement(header, "VendorModelVersion").text = "1.0"

    maintenance = ET.SubElement(root, "ItemMaintenance")
    ET.SubElement(
        maintenance, "TableAction", {"type": "addchange"},
    )
    for item in items:
        detail = ET.SubElement(maintenance, "ITTDetail")
        data = ET.SubElement(detail, "ITTData")
        code_el = ET.SubElement(data, "ItemCode")
        ET.SubElement(code_el, "POSCodeFormat", {
            "format": _FORMAT_MAP.get(
                item.pos_code_format or "upc", "upcA",
            ),
        })
        ET.SubElement(code_el, "POSCode").text = item.pos_code or ""
        ET.SubElement(data, "Description").text = (
            (item.name or "")[:40]  # register display width
        )
        merch = (
            merch_by_dept.get(int(item.department_id))
            if item.department_id is not None else None
        )
        if merch:
            ET.SubElement(data, "MerchandiseCode").text = merch
        ET.SubElement(data, "RegularSellPrice").text = (
            f"{(item.price_cents or 0) / 100.0:.2f}"
        )
        ET.SubElement(data, "ActiveFlag", {"value": "yes"})

    xml = ET.tostring(root, encoding="unicode", xml_declaration=False)
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n' + xml,
        len(items),
    )


__all__ = ["export_items"]
