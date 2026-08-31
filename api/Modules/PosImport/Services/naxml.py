"""Gilbarco Passport NAXML-POSJournal parser (P1-9 — the market
wedge, HANDOFF.md §2).

Passport writes one PJR*.xml file per register event to its
back-office share. Each file is a ``NAXML-POSJournal`` document
holding exactly one event — a sale, refund, void, register
open/close ("other"), or financial event (safe drop). This module
turns those files into typed events and rolls a batch of them up
into per-(business day, register) aggregates that map 1:1 onto
the DayClose module's RegisterClose + DepartmentSale shapes.

Ground truth from a real Passport 22.01 site (23 business days,
~17.7k files — see task #97):

* ``BusinessDate`` is authoritative: the register's business day
  rolls at the site's day close (e.g. ~22:50), NOT midnight, and
  every event carries the day it belongs to.
* Refund events carry NEGATIVE amounts end-to-end (summary and
  tenders), so plain summation nets them out of a day.
* Void events contain only ``status="cancel"`` lines. Those lines
  are PARSED and kept (G-5 — an operator needs to see that an item
  was voided mid-sale), flagged ``status="cancel"``, and excluded
  from every money total. A void event therefore still nets to
  zero, but is no longer invisible.
* ``MerchandiseCode`` is the site's numeric department. Fuel
  lines (``FuelLine``) additionally carry the grade, gallons
  (3-decimal quantity), and pump position.
* Change back to the customer appears as a negative cash tender
  with ``ChangeFlag="yes"`` — summing tenders as-is yields net
  cash taken in.

The XML arrives from customer sites — untrusted input — so it is
parsed exclusively through defusedxml. Money is integer cents
(P0-3); gallons stay floats (volume, not money — same rationale
as ``StoreEmployee.hourly_rate``).

Parse errors raise ``PosJournalParseError`` with a user-safe
message; the caller decides whether a bad file poisons a batch or
is just reported and skipped.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime

from defusedxml import ElementTree as SafeET

from api.Core.Money import to_cents


class PosJournalParseError(Exception):
    """Malformed / non-POSJournal input (message is user-safe)."""


# NAXML event tag → our event kind.
_EVENT_KINDS = {
    "SaleEvent": "sale",
    "RefundEvent": "refund",
    "VoidEvent": "void",
    "OtherEvent": "other",
    "FinancialEvent": "financial",
}

# Tender codes that mean "a card network settles this" — includes
# the outside (pay-at-pump) variants.
CARD_TENDER_CODES = frozenset({
    "creditCards", "debitCards", "outsideCredit", "outsideDebit",
    "outsideMobileCredit", "outsideMobileDebit",
})
CASH_TENDER_CODES = frozenset({"cash"})


# TransactionLine status="cancel" — a line the register itself
# discarded (a voided item, a mis-scan corrected mid-sale).
LINE_STATUS_NORMAL = "normal"
LINE_STATUS_CANCEL = "cancel"


@dataclass
class PjrItemLine:
    merchandise_code: str
    description: str
    quantity: float
    amount_cents: int
    is_fuel: bool = False
    fuel_grade_id: str = ""
    fuel_position: str = ""
    gallons: float = 0.0
    # Item identity for the price-book warm start (P2-3): the scan
    # code (UPC digits or keyed PLU), its format, and the shelf
    # price at the time of sale. Fuel lines carry none of these.
    pos_code: str = ""
    pos_code_format: str = ""
    regular_price_cents: int = 0
    # G-5 additions — for the transaction viewer, not the money math.
    #
    # `status` is the load-bearing one. Cancelled lines used to be
    # dropped during parse; they are now kept so an operator can see
    # that an item WAS voided mid-sale (a real loss-prevention
    # signal). Everything that computes money MUST filter on
    # `status == LINE_STATUS_NORMAL` — `aggregate_events` does, and
    # a cancelled line reaching a day total would silently inflate
    # it.
    status: str = LINE_STATUS_NORMAL
    line_seq: int = 0
    entry_method: str = ""
    actual_price_cents: int = 0
    selling_units: str = ""
    tax_level_id: str = ""


@dataclass
class PjrTender:
    code: str
    sub_code: str
    amount_cents: int
    is_change: bool
    # Same rule as PjrItemLine.status — a tender on a cancelled
    # line never counts toward a drawer total.
    status: str = LINE_STATUS_NORMAL


# Aggregation key + display label for pay-at-pump activity. All
# outside (OutsideSalesFlag="yes") events collapse into one
# virtual register per day: pump registers carry synthetic IDs
# (10008, …) that operators never reconcile individually.
OUTSIDE_REGISTER_KEY = "outside"
OUTSIDE_REGISTER_LABEL = "Pay at pump"


@dataclass
class PjrEvent:
    kind: str
    business_date: date | None
    register_id: str
    cashier_id: str
    till_id: str
    transaction_id: str
    outside: bool = False
    # Clock hour 0-23 of the event (G-3, hourly sales). Sourced
    # from the first timestamp the file offers (see _event_hour);
    # None when the file carries none — hourly charts simply skip
    # such events, day totals are unaffected.
    event_hour: int | None = None
    items: list[PjrItemLine] = field(default_factory=list)
    tenders: list[PjrTender] = field(default_factory=list)
    gross_cents: int = 0
    net_cents: int = 0
    tax_cents: int = 0
    # OtherEvent register-open detail: the opening drawer float.
    opening_cash_cents: int | None = None
    # G-5 — event detail for the transaction viewer. None/"" when
    # the file omits them; nothing here feeds a money total.
    event_sequence_id: str = ""
    started_at: datetime | None = None
    ended_at: datetime | None = None
    receipt_at: datetime | None = None
    training_mode: bool = False
    offline: bool = False
    suspended: bool = False
    grand_total_cents: int = 0
    # Filename the event was parsed from. Set by the caller that
    # loaded it (parse_pjr sees bytes, not a name); it is what makes
    # the persisted transaction idempotent across re-commits — one
    # event per file, so re-parsing replaces rather than duplicates.
    source_file: str = ""


def _text(el, tag: str) -> str:
    found = el.find(".//" + tag)
    if found is None or found.text is None:
        return ""
    return found.text.strip()


def _cents(el, tag: str) -> int:
    raw = _text(el, tag)
    if not raw:
        return 0
    try:
        return to_cents(raw)
    except ValueError:
        raise PosJournalParseError(
            f"Bad money value {raw!r} in <{tag}>",
        )


def _float(el, tag: str) -> float:
    raw = _text(el, tag)
    if not raw:
        return 0.0
    try:
        return float(raw)
    except ValueError:
        raise PosJournalParseError(
            f"Bad numeric value {raw!r} in <{tag}>",
        )


def _flag(el, tag: str) -> bool:
    """NAXML boolean flags are an attribute, not text:
    ``<TrainingModeFlag value="no"/>``."""
    found = el.find(".//" + tag)
    return found is not None and (found.get("value") or "") == "yes"


def _date(el, tag: str) -> date | None:
    raw = _text(el, tag)
    if not raw:
        return None
    try:
        return datetime.strptime(raw, "%Y-%m-%d").date()
    except ValueError:
        raise PosJournalParseError(
            f"Bad date {raw!r} in <{tag}>",
        )


def _stamp(el, date_tag: str, time_tag: str) -> datetime | None:
    """Combine a sibling <XxxDate> + <XxxTime> pair into a datetime.

    Returns None when either half is missing or unparseable —
    timestamps are display detail, so a malformed one must never
    fail a parse that would otherwise book money correctly.
    """
    d = _text(el, date_tag)
    t = _text(el, time_tag) or "00:00:00"
    if not d:
        return None
    try:
        return datetime.strptime(f"{d} {t[:8]}", "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None


def _event_hour(root, event_el) -> int | None:
    """Best-effort clock hour for the event (G-3). Sites vary in
    which timestamp the journal carries, so try candidates in
    priority order and degrade to None — a missing hour only mutes
    the hourly chart, never a day total:

      1. event-level <EventDateTime> / <EventStartDateTime>
         (ISO "2024-10-14T13:45:12"),
      2. the JournalHeader's <BeginTime> ("13:45:12") — one file
         per event, so the header time is the event time.
    """
    for tag in ("EventDateTime", "EventStartDateTime"):
        raw = _text(event_el, tag)
        if "T" in raw:
            try:
                hour = int(raw.split("T", 1)[1][:2])
            except ValueError:
                continue
            if 0 <= hour <= 23:
                return hour
    raw = _text(root, "BeginTime")
    if raw and ":" in raw:
        try:
            hour = int(raw.split(":", 1)[0])
        except ValueError:
            return None
        if 0 <= hour <= 23:
            return hour
    return None


def _parse_item_line(line_el, *, status: str = LINE_STATUS_NORMAL,
                     line_seq: int = 0) -> list[PjrItemLine]:
    """Every ItemLine / FuelLine under one TransactionLine.

    `status` is the parent TransactionLine's — a cancelled line's
    items are kept (so the viewer can show what was voided) and
    carry the flag that keeps them out of every money total.
    """
    items: list[PjrItemLine] = []
    for item in line_el.findall(".//ItemLine"):
        fmt_el = item.find(".//ItemCode/POSCodeFormat")
        entry_el = item.find(".//EntryMethod")
        items.append(PjrItemLine(
            merchandise_code=_text(item, "MerchandiseCode"),
            description=_text(item, "Description"),
            quantity=_float(item, "SalesQuantity"),
            amount_cents=_cents(item, "SalesAmount"),
            pos_code=_text(item, "ItemCode/POSCode"),
            pos_code_format=(
                (fmt_el.get("format") or "") if fmt_el is not None else ""
            ),
            regular_price_cents=_cents(item, "RegularSellPrice"),
            status=status,
            line_seq=line_seq,
            entry_method=(
                (entry_el.get("method") or "") if entry_el is not None else ""
            ),
            actual_price_cents=_cents(item, "ActualSalesPrice"),
            selling_units=_text(item, "SellingUnits"),
            tax_level_id=_text(item, "ItemTax/TaxLevelID"),
        ))
    for fuel in line_el.findall(".//FuelLine"):
        items.append(PjrItemLine(
            merchandise_code=_text(fuel, "MerchandiseCode"),
            description=_text(fuel, "Description"),
            quantity=_float(fuel, "SalesQuantity"),
            amount_cents=_cents(fuel, "SalesAmount"),
            is_fuel=True,
            fuel_grade_id=_text(fuel, "FuelGradeID"),
            fuel_position=_text(fuel, "FuelPositionID"),
            gallons=_float(fuel, "SalesQuantity"),
            status=status,
            line_seq=line_seq,
            actual_price_cents=_cents(fuel, "ActualSalesPrice"),
        ))
    return items


def parse_pjr(data: bytes | str) -> PjrEvent:
    """Parse one PJR*.xml POSJournal file into a typed event."""
    if isinstance(data, str):
        data = data.encode("ISO-8859-1", errors="replace")
    try:
        root = SafeET.fromstring(data)
    except Exception:
        raise PosJournalParseError("Not well-formed XML.")
    if "POSJournal" not in (root.tag or ""):
        raise PosJournalParseError(
            "Not a NAXML POSJournal document "
            f"(root <{root.tag}>).",
        )

    event_el = None
    kind = ""
    for tag, k in _EVENT_KINDS.items():
        event_el = root.find(".//" + tag)
        if event_el is not None:
            kind = k
            break
    if event_el is None:
        raise PosJournalParseError(
            "POSJournal contains no recognized event.",
        )

    outside_el = event_el.find(".//OutsideSalesFlag")
    event = PjrEvent(
        kind=kind,
        business_date=_date(event_el, "BusinessDate"),
        register_id=_text(event_el, "RegisterID"),
        cashier_id=_text(event_el, "CashierID"),
        till_id=_text(event_el, "TillID"),
        transaction_id=_text(event_el, "TransactionID"),
        outside=(
            outside_el is not None and outside_el.get("value") == "yes"
        ),
        event_hour=_event_hour(root, event_el),
        event_sequence_id=_text(event_el, "EventSequenceID"),
        started_at=_stamp(event_el, "EventStartDate", "EventStartTime"),
        ended_at=_stamp(event_el, "EventEndDate", "EventEndTime"),
        receipt_at=_stamp(event_el, "ReceiptDate", "ReceiptTime"),
        training_mode=_flag(event_el, "TrainingModeFlag"),
        offline=_flag(event_el, "OfflineFlag"),
        suspended=_flag(event_el, "SuspendFlag"),
    )

    # Register open/close detail (OtherEvent): opening drawer cash.
    detail = event_el.find(".//RegisterDetail")
    if detail is not None and detail.get("detailType") == "open":
        event.opening_cash_cents = _cents(detail, "CashInDrawer")

    for seq, line in enumerate(event_el.findall(".//TransactionLine"), 1):
        # Cancelled lines are corrections the register already
        # discarded — voided items, mis-scans. They are KEPT here
        # (G-5: an operator wants to see that something was voided
        # mid-sale) and flagged, so everything downstream that
        # computes money can filter them out. `aggregate_events`
        # does exactly that; day totals are unchanged.
        status = (
            LINE_STATUS_CANCEL if line.get("status") == "cancel"
            else LINE_STATUS_NORMAL
        )
        event.items.extend(
            _parse_item_line(line, status=status, line_seq=seq),
        )
        for tender in line.findall(".//TenderInfo"):
            change_el = tender.find(".//ChangeFlag")
            event.tenders.append(PjrTender(
                code=_text(tender, "TenderCode"),
                sub_code=_text(tender, "TenderSubCode"),
                amount_cents=_cents(tender, "TenderAmount"),
                is_change=(
                    change_el is not None
                    and change_el.get("value") == "yes"
                ),
                status=status,
            ))

    summary = event_el.find(".//TransactionSummary")
    if summary is not None:
        event.gross_cents = _cents(summary, "TransactionTotalGrossAmount")
        event.net_cents = _cents(summary, "TransactionTotalNetAmount")
        event.tax_cents = _cents(summary, "TransactionTotalTaxNetAmount")
        event.grand_total_cents = _cents(
            summary, "TransactionTotalGrandAmount",
        )
    return event


# ── Day aggregation ────────────────────────────────────────


@dataclass
class FuelGradeAggregate:
    grade_id: str
    description: str
    gallons: float = 0.0
    amount_cents: int = 0


@dataclass
class RegisterDayAggregate:
    """One register's business day, rolled up from its journal
    events. Maps onto DayClose's RegisterClose + DepartmentSale:
    ``net_sales_cents`` → gross_sales (merchandise + fuel, refunds
    netted, pre-tax), ``tax_cents`` → sales_tax, tender buckets →
    cash/card/other totals, ``departments`` → department sale
    lines (keyed by the site's numeric MerchandiseCode — the
    operator maps codes to their Department catalog at review
    time)."""

    business_date: date
    register_id: str
    net_sales_cents: int = 0
    refunds_cents: int = 0
    tax_cents: int = 0
    cash_cents: int = 0
    card_cents: int = 0
    other_tender_cents: int = 0
    opening_cash_cents: int | None = None
    sale_count: int = 0
    refund_count: int = 0
    departments: dict[str, int] = field(default_factory=dict)
    fuel: dict[str, FuelGradeAggregate] = field(default_factory=dict)


def aggregate_events(
    events: list[PjrEvent],
) -> list[RegisterDayAggregate]:
    """Roll parsed events into per-(business day, register)
    aggregates, sorted by day then register. Events without a
    business date are ignored (they cannot be booked to a day);
    void events contribute nothing by construction (their lines
    are all cancelled)."""
    by_key: dict[tuple[date, str], RegisterDayAggregate] = {}
    for ev in events:
        if ev.business_date is None:
            continue
        register_key = (
            OUTSIDE_REGISTER_KEY if ev.outside else (ev.register_id or "")
        )
        key = (ev.business_date, register_key)
        agg = by_key.get(key)
        if agg is None:
            agg = RegisterDayAggregate(
                business_date=ev.business_date,
                register_id=register_key,
            )
            by_key[key] = agg

        if ev.kind == "other" and ev.opening_cash_cents is not None:
            # Register open — capture the first drawer float seen.
            if agg.opening_cash_cents is None:
                agg.opening_cash_cents = ev.opening_cash_cents
            continue
        if ev.kind not in ("sale", "refund"):
            continue

        if ev.kind == "sale":
            agg.sale_count += 1
        else:
            agg.refund_count += 1
            # Refund amounts are negative; track magnitude too.
            agg.refunds_cents += -ev.net_cents

        agg.net_sales_cents += ev.net_cents
        agg.tax_cents += ev.tax_cents
        for item in ev.items:
            # Voided lines are visible in the transaction viewer but
            # never money. Parsing keeps them; totals must not.
            if item.status != LINE_STATUS_NORMAL:
                continue
            code = item.merchandise_code or "?"
            agg.departments[code] = (
                agg.departments.get(code, 0) + item.amount_cents
            )
            if item.is_fuel:
                grade = agg.fuel.get(item.fuel_grade_id)
                if grade is None:
                    grade = FuelGradeAggregate(
                        grade_id=item.fuel_grade_id,
                        description=item.description,
                    )
                    agg.fuel[item.fuel_grade_id] = grade
                grade.gallons += item.gallons
                grade.amount_cents += item.amount_cents
        for tender in ev.tenders:
            if tender.status != LINE_STATUS_NORMAL:
                continue
            # Change lines are already negative — summing yields
            # net money taken in per tender bucket.
            if tender.code in CASH_TENDER_CODES:
                agg.cash_cents += tender.amount_cents
            elif tender.code in CARD_TENDER_CODES:
                agg.card_cents += tender.amount_cents
            else:
                agg.other_tender_cents += tender.amount_cents

    return sorted(
        by_key.values(),
        key=lambda a: (a.business_date, a.register_id),
    )


__all__ = [
    "CARD_TENDER_CODES", "CASH_TENDER_CODES",
    "LINE_STATUS_CANCEL", "LINE_STATUS_NORMAL", "FuelGradeAggregate",
    "OUTSIDE_REGISTER_KEY", "OUTSIDE_REGISTER_LABEL",
    "PjrEvent", "PjrItemLine", "PjrTender", "PosJournalParseError",
    "RegisterDayAggregate", "aggregate_events", "parse_pjr",
]
