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


def rebuild_hourly_sales(
    db: Session, store_id: int, day: date, events: list[PjrEvent],
) -> int:
    """Replace the day's HourlySale rows from its events (G-3).
    Runs at every (re)commit so booked history is always the sum
    of the staged originals — the live per-upload increments in
    ``agent.stage_journal_file`` are a running preview this
    rebuild self-heals. Events without a clock hour are skipped
    (they still count toward day totals, just not the chart)."""
    from api.Modules.DayClose.Models import HourlySale

    sums: dict[int, int] = {}
    for e in events:
        if e.kind not in ("sale", "refund"):
            continue
        if e.business_date != day or e.event_hour is None:
            continue
        sums[e.event_hour] = sums.get(e.event_hour, 0) + e.net_cents
    (
        db.query(HourlySale)
        .filter_by(
            store_id=store_id, report_date=day, source=IMPORT_SOURCE,
        )
        .delete()
    )
    for hour, cents in sorted(sums.items()):
        db.add(HourlySale(
            store_id=store_id, report_date=day, hour=hour,
            amount_cents=cents, source=IMPORT_SOURCE,
        ))
    db.flush()
    return len(sums)


def rebuild_item_day_sales(
    db: Session, store_id: int, day: date, events: list[PjrEvent],
) -> int:
    """Replace the day's per-item movement rows from its events
    (G-2). Same delete-and-rebuild posture as the hourly buckets:
    every (re)commit makes the stored movement the exact sum of
    the staged originals. Refund quantities/amounts are negative
    end-to-end so they net out, and fuel/code-less lines are
    excluded (fuel is grade volume; a code-less line can't be
    tracked as an item).

    Cancelled lines are skipped HERE. They used to be dropped at
    parse time; G-5 keeps them so the transaction viewer can show a
    voided item, which means every consumer that sums money now
    owns the filter. Selling a $5.49 item and voiding it mid-sale
    must move zero units."""
    from api.Modules.PosImport.Models import PosItemDaySale
    from api.Modules.PosImport.Services.naxml import LINE_STATUS_NORMAL

    qty: dict[str, float] = {}
    cents: dict[str, int] = {}
    desc: dict[str, str] = {}
    merch: dict[str, str] = {}
    for e in events:
        if e.kind not in ("sale", "refund") or e.business_date != day:
            continue
        for line in e.items:
            if line.status != LINE_STATUS_NORMAL:
                continue
            if line.is_fuel or not line.pos_code:
                continue
            code = line.pos_code
            qty[code] = qty.get(code, 0.0) + float(line.quantity or 0)
            cents[code] = cents.get(code, 0) + int(line.amount_cents or 0)
            if line.description:
                desc[code] = line.description
            if line.merchandise_code:
                merch[code] = line.merchandise_code
    (
        db.query(PosItemDaySale)
        .filter_by(store_id=store_id, business_date=day)
        .delete()
    )
    for code in sorted(cents):
        db.add(PosItemDaySale(
            store_id=store_id,
            business_date=day,
            pos_code=code,
            description=desc.get(code, "")[:160],
            merchandise_code=merch.get(code, "")[:20],
            quantity=round(qty.get(code, 0.0), 3),
            amount_cents=cents[code],
        ))
    db.flush()
    return len(cents)


def rebuild_transactions(
    db: Session, store_id: int, day: date, events: list[PjrEvent],
) -> int:
    """Replace the day's persisted transactions from its events
    (G-5). Same delete-and-rebuild posture as the hourly buckets and
    item movement: after every (re)commit the stored transactions
    are exactly what the staged originals say.

    Unlike the aggregates, this keeps EVERYTHING — refunds, voids,
    register opens, financial events, and the individual lines the
    register cancelled mid-sale. Nothing here is summed into a
    total, so nothing needs filtering out; the callers that DO sum
    (aggregate_events, rebuild_item_day_sales) own that filter.

    Events with no ``source_file`` are skipped: without it there is
    no idempotence key, and a re-commit would duplicate them.
    """
    from api.Modules.PosImport.Models import (
        PosTransaction, PosTransactionLine, PosTransactionTender,
    )
    from api.Modules.PosImport.Services.naxml import LINE_STATUS_NORMAL

    # Children go first — the FK is ON DELETE CASCADE in Postgres,
    # but SQLite doesn't enforce it by default, so be explicit.
    existing = [
        row.id for row in
        db.query(PosTransaction.id)
        .filter_by(store_id=store_id, business_date=day)
        .all()
    ]
    if existing:
        for model in (PosTransactionLine, PosTransactionTender):
            (
                db.query(model)
                .filter(model.transaction_id.in_(existing))
                .delete(synchronize_session=False)
            )
        (
            db.query(PosTransaction)
            .filter(PosTransaction.id.in_(existing))
            .delete(synchronize_session=False)
        )
        db.flush()

    written = 0
    for e in events:
        if e.business_date != day or not e.source_file:
            continue
        txn = PosTransaction(
            store_id=store_id,
            business_date=day,
            source_file=e.source_file[:120],
            kind=e.kind,
            register_id=(e.register_id or "")[:20],
            cashier_id=(e.cashier_id or "")[:20],
            till_id=(e.till_id or "")[:20],
            transaction_no=(e.transaction_id or "")[:30],
            event_sequence_id=(e.event_sequence_id or "")[:20],
            started_at=e.started_at,
            ended_at=e.ended_at,
            receipt_at=e.receipt_at,
            event_hour=e.event_hour,
            outside=e.outside,
            training_mode=e.training_mode,
            offline=e.offline,
            suspended=e.suspended,
            gross_cents=e.gross_cents,
            net_cents=e.net_cents,
            tax_cents=e.tax_cents,
            grand_total_cents=e.grand_total_cents,
            has_voided_line=any(
                i.status != LINE_STATUS_NORMAL for i in e.items
            ),
        )
        db.add(txn)
        db.flush()  # need txn.id for the children

        for line in e.items:
            db.add(PosTransactionLine(
                transaction_id=txn.id,
                store_id=store_id,
                business_date=day,
                line_seq=line.line_seq,
                status=line.status,
                pos_code=(line.pos_code or "")[:30],
                pos_code_format=(line.pos_code_format or "")[:20],
                description=(line.description or "")[:160],
                entry_method=(line.entry_method or "")[:20],
                merchandise_code=(line.merchandise_code or "")[:20],
                selling_units=(line.selling_units or "")[:20],
                tax_level_id=(line.tax_level_id or "")[:20],
                quantity=float(line.quantity or 0),
                amount_cents=int(line.amount_cents or 0),
                actual_price_cents=int(line.actual_price_cents or 0),
                regular_price_cents=int(line.regular_price_cents or 0),
                is_fuel=line.is_fuel,
                fuel_grade_id=(line.fuel_grade_id or "")[:10],
                fuel_position=(line.fuel_position or "")[:10],
                gallons=float(line.gallons or 0),
            ))
        for tender in e.tenders:
            db.add(PosTransactionTender(
                transaction_id=txn.id,
                store_id=store_id,
                business_date=day,
                status=tender.status,
                code=(tender.code or "")[:30],
                sub_code=(tender.sub_code or "")[:30],
                amount_cents=int(tender.amount_cents or 0),
                is_change=tender.is_change,
            ))
        written += 1

    db.flush()
    return written


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
    rebuild_hourly_sales(db, store_id, day, events)
    rebuild_item_day_sales(db, store_id, day, events)
    rebuild_transactions(db, store_id, day, events)
    return CommitDayResult(
        day=day, closes_written=len(days), registers=registers,
    )


__all__ = [
    "CommitDayResult", "IMPORT_SOURCE", "LoadedPayload",
    "MAX_PAYLOAD_BYTES", "PosImportError", "commit_business_day",
    "list_mappings", "load_pjr_payload", "mapping_status",
    "rebuild_hourly_sales", "rebuild_item_day_sales",
    "rebuild_transactions",
    "register_label_for", "set_mappings",
]
