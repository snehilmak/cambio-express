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
* Void events contain only ``status="cancel"`` lines — skipping
  cancelled lines (which we must do everywhere) zeroes them.
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


@dataclass
class PjrTender:
    code: str
    sub_code: str
    amount_cents: int
    is_change: bool


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
    items: list[PjrItemLine] = field(default_factory=list)
    tenders: list[PjrTender] = field(default_factory=list)
    gross_cents: int = 0
    net_cents: int = 0
    tax_cents: int = 0
    # OtherEvent register-open detail: the opening drawer float.
    opening_cash_cents: int | None = None


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


def _parse_item_line(line_el) -> list[PjrItemLine]:
    items: list[PjrItemLine] = []
    for item in line_el.findall(".//ItemLine"):
        items.append(PjrItemLine(
            merchandise_code=_text(item, "MerchandiseCode"),
            description=_text(item, "Description"),
            quantity=_float(item, "SalesQuantity"),
            amount_cents=_cents(item, "SalesAmount"),
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
    )

    # Register open/close detail (OtherEvent): opening drawer cash.
    detail = event_el.find(".//RegisterDetail")
    if detail is not None and detail.get("detailType") == "open":
        event.opening_cash_cents = _cents(detail, "CashInDrawer")

    for line in event_el.findall(".//TransactionLine"):
        # Cancelled lines are corrections the register already
        # discarded — voided items, mis-scans. Never count them.
        if line.get("status") == "cancel":
            continue
        event.items.extend(_parse_item_line(line))
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
            ))

    summary = event_el.find(".//TransactionSummary")
    if summary is not None:
        event.gross_cents = _cents(summary, "TransactionTotalGrossAmount")
        event.net_cents = _cents(summary, "TransactionTotalNetAmount")
        event.tax_cents = _cents(summary, "TransactionTotalTaxNetAmount")
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
    "CARD_TENDER_CODES", "CASH_TENDER_CODES", "FuelGradeAggregate",
    "OUTSIDE_REGISTER_KEY", "OUTSIDE_REGISTER_LABEL",
    "PjrEvent", "PjrItemLine", "PjrTender", "PosJournalParseError",
    "RegisterDayAggregate", "aggregate_events", "parse_pjr",
]
