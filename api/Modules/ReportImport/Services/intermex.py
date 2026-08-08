"""Deterministic parser for Intermex "Reporte de cierre del día".

The Intermex daily close report is a text-based PDF (real text layer —
no OCR needed) with three transaction sections:

  * **Giros** — money transfers. Columns: ``Giro #``, ``Monto envío``
    (send), ``Cargo`` (fee), ``Imp. transac.`` (transaction tax),
    ``Balance`` (total collected), ``Creado por`` (cashier). Each row
    satisfies ``send + fee + tax == total`` — the same invariant as
    ``Transfer`` (``total_collected = send_amount + fee + federal_tax``,
    CLAUDE.md invariant #9), so a Giros row maps 1:1 onto a transfer.
  * **Money order** — columns ``MO #``, ``Monto``, ``Cargo``,
    ``Balance``, ``Creado por``. Feeds the daily book ``money_order``.
  * **Pago Facturas** — bill payments. Feeds ``bill_payment_charge``.

This module is PURE: it turns bytes/text into dataclasses and never
touches the DB or the ledger. Staging, operator review, and the commit
into ``Transfer`` rows are separate (later) PRs — money data goes
through a human before it lands.

Amounts are parsed exactly (``Decimal``) so the per-row reconciliation
check is exact, then exposed as ``float`` to match the ``Transfer``
model's column types.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation


class ReportParseError(ValueError):
    """Raised when the text doesn't look like an Intermex daily report
    (missing header, no sections, unreadable amounts)."""


# A money token: 1,700.00 / 288.12 / 8.00 — thousands optional, always
# two decimals (Intermex is consistent here).
_NUM = r"[\d,]+\.\d{2}"
_SECTION_NAMES = ("Giros", "Money order", "Pago Facturas")

# Giros: num[markers]  send  fee  tax  balance  cashier(may be glued to
# the balance because the source column is narrow, so `\s*` not `\s+`).
_GIRO_ROW = re.compile(
    rf"^(\d+)([*R]*)\s+({_NUM})\s+({_NUM})\s+({_NUM})\s+({_NUM})\s*([A-Za-zÀ-ÿ]*)$"
)
# Money order / Pago Facturas: num[markers]  amount  fee  balance  cashier
_THREE_COL_ROW = re.compile(
    rf"^(\d+)([*R]*)\s+({_NUM})\s+({_NUM})\s+({_NUM})\s+([A-Za-zÀ-ÿ]*)$"
)
# Stated section footer: "$3,621.79 $98.00 $3,756.00"
_TOTALS_ROW = re.compile(rf"^\$?({_NUM})\s+\$?({_NUM})\s+\$?({_NUM})$")
_COUNT_RE = re.compile(r"Total:\s*(\d+)")
_PROCESSED_RE = re.compile(r"Procesados:\s*(\d+)")
_VOIDED_RE = re.compile(r"Anulados:\s*(\d+)")


def _money(tok: str) -> Decimal:
    try:
        return Decimal(tok.replace(",", ""))
    except InvalidOperation as exc:  # pragma: no cover - guarded by regex
        raise ReportParseError(f"unreadable amount: {tok!r}") from exc


@dataclass(frozen=True)
class IntermexTxnRow:
    """One transaction row from any of the three sections.

    ``federal_tax`` is populated only for Giros (the ``Imp. transac.``
    column); Money orders and bill payments have no per-row tax so it's
    ``0.0`` there. ``reconciles`` is the Giros invariant
    (``send + fee + tax == total``) — always True for a clean Giros
    row; for Money order / Pago Facturas it is informational only
    (those settle by a different formula)."""
    section: str            # "giros" | "money_order" | "bill_payment"
    confirm_number: str
    send_amount: float      # Monto envío / Monto / Monto factura
    fee: float              # Cargo
    federal_tax: float      # Imp. transac. (Giros only)
    total_collected: float  # Balance
    cashier: str            # Creado por (may be column-truncated)
    cancelled: bool         # row flagged (*) — cancelled / anulado
    replacement: bool       # row flagged (R) — giro de reemplazo
    reconciles: bool


@dataclass(frozen=True)
class SectionTotals:
    """The stated per-section footer + the counts from its
    ``Total: N Procesados: N Anulados: N`` header line."""
    count: int
    processed: int
    voided: int
    amount: float   # Monto (send/face total)
    fees: float     # Total cargos
    balance: float  # Balance transac. (deposit total)


@dataclass
class IntermexDailyReport:
    """Parsed Intermex daily close report."""
    agency: str
    report_date: date | None
    giros: list[IntermexTxnRow] = field(default_factory=list)
    money_orders: list[IntermexTxnRow] = field(default_factory=list)
    bill_payments: list[IntermexTxnRow] = field(default_factory=list)
    giros_totals: SectionTotals | None = None
    money_order_totals: SectionTotals | None = None
    bill_payment_totals: SectionTotals | None = None

    @property
    def active_giros(self) -> list["IntermexTxnRow"]:
        """Giros that actually settled — cancelled/voided (*) rows
        drop out (they never become transfers, and the report excludes
        them from the deposit total)."""
        return [g for g in self.giros if not g.cancelled]

    @property
    def all_reconcile(self) -> bool:
        """True when every active Giros row reconciles AND the parsed
        active-Giros balance matches the report's stated Giros total —
        the signal that the money-transfer rows are safe to stage."""
        active = self.active_giros
        if not active:
            return False
        if not all(g.reconciles for g in active):
            return False
        if self.giros_totals is None:
            return True
        parsed = round(sum(g.total_collected for g in active), 2)
        return parsed == round(self.giros_totals.balance, 2)


def extract_pdf_text(data: bytes) -> str:
    """Concatenate the text layer of every page. Deterministic — no
    OCR. Raises ``ReportParseError`` if the PDF has no extractable text
    (i.e. it's a scan/photo, which needs the future vision path)."""
    import io

    import pdfplumber

    parts: list[str] = []
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        for page in pdf.pages:
            parts.append(page.extract_text() or "")
    text = "\n".join(parts)
    if not text.strip():
        raise ReportParseError(
            "no extractable text — the report looks scanned/photographed "
            "(needs the vision path, not the deterministic parser)."
        )
    return text


def parse_intermex_pdf(data: bytes) -> IntermexDailyReport:
    """Convenience: extract the PDF's text, then parse it."""
    return parse_intermex_text(extract_pdf_text(data))


def _parse_header(text: str) -> tuple[str, date | None]:
    agency_m = re.search(r"Agencia:\s*(.+)", text)
    if agency_m is None:
        raise ReportParseError("not an Intermex report: no 'Agencia:' header")
    agency = agency_m.group(1).strip()
    date_m = re.search(r"Fecha:\s*(\d{2})/(\d{2})/(\d{4})", text)
    report_date: date | None = None
    if date_m:
        mm, dd, yyyy = (int(g) for g in date_m.groups())
        try:
            report_date = date(yyyy, mm, dd)
        except ValueError:
            report_date = None
    return agency, report_date


def _section_totals(lines: list[str], header_line: str) -> SectionTotals | None:
    count = int(m.group(1)) if (m := _COUNT_RE.search(header_line)) else 0
    processed = int(m.group(1)) if (m := _PROCESSED_RE.search(header_line)) else 0
    voided = int(m.group(1)) if (m := _VOIDED_RE.search(header_line)) else 0
    for ln in lines:
        tm = _TOTALS_ROW.match(ln.strip())
        if tm:
            return SectionTotals(
                count=count, processed=processed, voided=voided,
                amount=float(_money(tm.group(1))),
                fees=float(_money(tm.group(2))),
                balance=float(_money(tm.group(3))),
            )
    if count or processed or voided:
        return SectionTotals(count, processed, voided, 0.0, 0.0, 0.0)
    return None


def _giro_row(m: "re.Match[str]") -> IntermexTxnRow:
    num, marks, send, fee, tax, bal, who = m.groups()
    s, f, t, b = (_money(send), _money(fee), _money(tax), _money(bal))
    return IntermexTxnRow(
        section="giros", confirm_number=num,
        send_amount=float(s), fee=float(f), federal_tax=float(t),
        total_collected=float(b), cashier=who,
        cancelled="*" in marks, replacement="R" in marks,
        reconciles=(s + f + t == b),
    )


def _three_col_row(m: "re.Match[str]", section: str) -> IntermexTxnRow:
    num, marks, amount, fee, bal, who = m.groups()
    a, f, b = (_money(amount), _money(fee), _money(bal))
    return IntermexTxnRow(
        section=section, confirm_number=num,
        send_amount=float(a), fee=float(f), federal_tax=0.0,
        total_collected=float(b), cashier=who,
        cancelled="*" in marks, replacement="R" in marks,
        reconciles=(a + f == b),
    )


def parse_intermex_text(text: str) -> IntermexDailyReport:
    """Parse the extracted text of an Intermex daily close report.

    Walks the report top-to-bottom with a tiny state machine: a line
    that is exactly a section name (``Giros`` / ``Money order`` /
    ``Pago Facturas``) and is immediately followed by a ``Total:`` line
    opens that section; rows are matched with the section-appropriate
    regex; the ``$x $y $z`` footer closes it."""
    agency, report_date = _parse_header(text)
    report = IntermexDailyReport(agency=agency, report_date=report_date)

    lines = text.splitlines()
    section: str | None = None
    header_line = ""
    section_lines: list[str] = []

    def flush(sec: str | None, hdr: str, body: list[str]) -> None:
        if sec is None:
            return
        totals = _section_totals(body, hdr)
        if sec == "giros":
            report.giros_totals = totals
        elif sec == "money_order":
            report.money_order_totals = totals
        elif sec == "bill_payment":
            report.bill_payment_totals = totals

    for idx, raw in enumerate(lines):
        line = raw.strip()
        nxt = lines[idx + 1].strip() if idx + 1 < len(lines) else ""
        # A bare section name immediately above a "Total:" line starts a
        # section (the same words also appear in the summary block, but
        # never directly above "Total:").
        if line in _SECTION_NAMES and nxt.startswith("Total:"):
            flush(section, header_line, section_lines)
            section = {
                "Giros": "giros",
                "Money order": "money_order",
                "Pago Facturas": "bill_payment",
            }[line]
            header_line = nxt
            section_lines = []
            continue
        if section is None:
            continue
        section_lines.append(line)
        if section == "giros":
            gm = _GIRO_ROW.match(line)
            if gm:
                report.giros.append(_giro_row(gm))
        else:
            tm = _THREE_COL_ROW.match(line)
            if tm:
                row = _three_col_row(tm, section)
                if section == "money_order":
                    report.money_orders.append(row)
                else:
                    report.bill_payments.append(row)

    flush(section, header_line, section_lines)

    if not (report.giros or report.money_orders or report.bill_payments):
        raise ReportParseError(
            "no transaction rows found — layout may have changed or this "
            "isn't an Intermex daily close report."
        )
    return report
