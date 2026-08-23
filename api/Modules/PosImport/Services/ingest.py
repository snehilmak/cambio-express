"""PosImport — ingest: payload loading, preview, commit.

The upload contract mirrors ReportImport's Intermex flow: the
client sends raw bytes (one PJR XML, or a ZIP of many) base64'd
in a JSON body; preview parses in memory and returns the day
aggregates + mapping status; commit RE-PARSES server-side (the
client never sends money numbers) and books ONE business day into
the DayClose module via ``upsert_register_close`` with
``source="gilbarco"``.

Commit is a hard gate on the merchandise-code mapping: any code
present in the day's data that has no ``PosMerchandiseMap`` row
blocks the commit with the offending codes listed — the operator
maps codes to their own Department catalog first (HANDOFF.md §2
product principle: the site's numeric codes MEAN whatever the
operator says they mean).

Re-importing the same day replaces the previously imported
closes (the DayClose upsert key), so re-running after a fix is
safe and idempotent.
"""
from __future__ import annotations

import io
import zipfile
from dataclasses import dataclass, field
from datetime import date

from sqlalchemy.orm import Session

from api.Modules.DayClose.Models import Department
from api.Modules.DayClose.Services import upsert_register_close
from api.Modules.PosImport.Models import PosMerchandiseMap
from api.Modules.PosImport.Services.naxml import (
    OUTSIDE_REGISTER_KEY,
    OUTSIDE_REGISTER_LABEL,
    PjrEvent,
    PosJournalParseError,
    RegisterDayAggregate,
    aggregate_events,
    parse_pjr,
)

# Decoded-payload ceiling. A full month of journals from a busy
# site is ~135MB raw; a single day is a few MB. Zips compress
# ~10x. Anything past this is almost certainly a mistake.
MAX_PAYLOAD_BYTES = 256 * 1024 * 1024
MAX_ZIP_MEMBERS = 40_000

IMPORT_SOURCE = "gilbarco"


class PosImportError(Exception):
    """User-safe ingest failure (bad payload, unmapped codes…)."""


@dataclass
class LoadedPayload:
    events: list[PjrEvent] = field(default_factory=list)
    parse_errors: list[str] = field(default_factory=list)  # "name: why"
    file_count: int = 0


def load_pjr_payload(data: bytes) -> LoadedPayload:
    """Decode an upload — a single PJR XML document or a ZIP of
    them — into parsed events. Individual bad files are reported,
    not fatal; a payload with zero parseable events is."""
    if len(data) > MAX_PAYLOAD_BYTES:
        raise PosImportError("Upload too large.")
    loaded = LoadedPayload()
    if data[:2] == b"PK":
        try:
            archive = zipfile.ZipFile(io.BytesIO(data))
        except zipfile.BadZipFile:
            raise PosImportError("Corrupt ZIP archive.")
        names = [
            n for n in archive.namelist()
            if n.lower().endswith(".xml") and not n.endswith("/")
        ]
        if len(names) > MAX_ZIP_MEMBERS:
            raise PosImportError("ZIP contains too many files.")
        for name in names:
            loaded.file_count += 1
            try:
                with archive.open(name) as f:
                    loaded.events.append(parse_pjr(f.read(4 * 1024 * 1024)))
            except PosJournalParseError as exc:
                loaded.parse_errors.append(f"{name.rsplit('/', 1)[-1]}: {exc}")
    else:
        loaded.file_count = 1
        try:
            loaded.events.append(parse_pjr(data))
        except PosJournalParseError as exc:
            loaded.parse_errors.append(f"upload: {exc}")
    if not loaded.events:
        raise PosImportError(
            "No parseable POS journal files in the upload."
            + (f" First error: {loaded.parse_errors[0]}"
               if loaded.parse_errors else ""),
        )
    return loaded


# ── Mapping ────────────────────────────────────────────────


def list_mappings(db: Session, store_id: int) -> list[PosMerchandiseMap]:
    return (
        db.query(PosMerchandiseMap)
        .filter_by(store_id=store_id)
        .order_by(PosMerchandiseMap.merchandise_code)
        .all()
    )


def set_mappings(
    db: Session, store_id: int, mappings: dict[str, int],
) -> list[PosMerchandiseMap]:
    """Upsert merchandise-code → department mappings. Departments
    must belong to the store; unknown ids fail the whole write."""
    if mappings:
        dept_ids = set(mappings.values())
        owned = {
            d.id for d in db.query(Department)
            .filter(
                Department.store_id == store_id,
                Department.id.in_(dept_ids),
            )
            .all()
        }
        if dept_ids - owned:
            raise PosImportError("Department not found")
    existing = {m.merchandise_code: m for m in list_mappings(db, store_id)}
    for code, dept_id in mappings.items():
        code = code.strip()
        if not code:
            continue
        row = existing.get(code)
        if row is None:
            db.add(PosMerchandiseMap(
                store_id=store_id, merchandise_code=code,
                department_id=dept_id,
            ))
        else:
            row.department_id = dept_id
    db.flush()
    return list_mappings(db, store_id)


def mapping_status(
    db: Session, store_id: int, days: list[RegisterDayAggregate],
) -> tuple[dict[str, int], list[str]]:
    """(code → department_id) for every code seen in the data,
    plus the sorted list of codes with no mapping yet."""
    seen: set[str] = set()
    for agg in days:
        seen.update(agg.departments.keys())
    mapped = {
        m.merchandise_code: int(m.department_id)
        for m in list_mappings(db, store_id)
        if m.merchandise_code in seen
    }
    unmapped = sorted(seen - set(mapped), key=lambda c: (len(c), c))
    return mapped, unmapped


# ── Commit ─────────────────────────────────────────────────


def register_label_for(register_key: str) -> str:
    if register_key == OUTSIDE_REGISTER_KEY:
        return OUTSIDE_REGISTER_LABEL
    return f"Register {register_key}" if register_key else "Register"


@dataclass
class CommitDayResult:
    day: date
    closes_written: int
    registers: list[str]


def commit_business_day(
    db: Session, store_id: int, day: date, *,
    events: list[PjrEvent], created_by: int | None,
) -> CommitDayResult:
    """Book one business day's aggregates into DayClose. Leaves
    commit to the Controller (invariant #7 pattern)."""
    days = [
        a for a in aggregate_events(events) if a.business_date == day
    ]
    if not days:
        raise PosImportError(
            f"The upload has no activity for {day.isoformat()}.",
        )
    mapped, unmapped = mapping_status(db, store_id, days)
    if unmapped:
        raise PosImportError(
            "Unmapped merchandise codes: " + ", ".join(unmapped)
            + ". Map every code to one of your departments first.",
        )

    registers: list[str] = []
    for agg in days:
        dept_sales: dict[int, float] = {}
        for code, cents in agg.departments.items():
            dept_id = mapped[code]
            # Two codes may map to one department — sum them. Skip
            # non-positive nets: DayClose lines are sales amounts.
            dept_sales[dept_id] = dept_sales.get(dept_id, 0.0) + cents / 100.0
        dept_sales = {
            k: round(v, 2) for k, v in dept_sales.items() if v > 0
        }
        label = register_label_for(agg.register_id)
        note = (
            f"Imported from Gilbarco journal — {agg.sale_count} sales"
            + (f", {agg.refund_count} refunds" if agg.refund_count else "")
        )
        upsert_register_close(
            db, store_id, day,
            register_label=label,
            shift_label="",
            gross_sales=agg.net_sales_cents / 100.0,
            sales_tax=agg.tax_cents / 100.0,
            cash_total=agg.cash_cents / 100.0,
            card_total=agg.card_cents / 100.0,
            other_total=agg.other_tender_cents / 100.0,
            cash_counted=None,
            notes=note[:500],
            department_sales=dept_sales,
            created_by=created_by,
            source=IMPORT_SOURCE,
        )
        registers.append(label)
    return CommitDayResult(
        day=day, closes_written=len(days), registers=registers,
    )


__all__ = [
    "CommitDayResult", "IMPORT_SOURCE", "LoadedPayload",
    "MAX_PAYLOAD_BYTES", "PosImportError", "commit_business_day",
    "list_mappings", "load_pjr_payload", "mapping_status",
    "register_label_for", "set_mappings",
]
