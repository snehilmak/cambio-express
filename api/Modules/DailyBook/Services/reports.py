"""Daily-book summary + lifecycle services.

Read-side:
  summarize_report — one DailyReport, with the derived
                     receipts/disbursements/net totals.
  summarize_period — list of reports + per-store + grand totals
                     across a date range.

Write-side (lock / unlock / ensure):
  ensure_daily_report — fetch-or-create the (store, date) row.
  lock_report — set locked_at/locked_by; idempotent if already locked.
  unlock_report — clear locked_at/locked_by; no-op if no row exists.
"""
from dataclasses import dataclass
from datetime import date
from typing import Iterable

from sqlalchemy.orm import Session

from api.Modules.DailyBook.Models import DailyReport
from api.Modules.DailyBook.Repositories import (
    find_prior_report,
    find_report_by_date,
    list_reports_in_period,
)
from api.Core.Clock import utc_now


@dataclass
class DailyReportSummary:
    """Wire-shape for one DailyReport. Receipts / disbursements /
    net are derived (Python-side) from the model's @property fields
    so the frontend doesn't have to recompute them.

    Full field set mirrors the SQLAlchemy DailyReport model — the
    React editor needs every input so it can hydrate the form on
    page load + show real-time totals as the cashier types."""
    id: int
    store_id: int
    report_date: str  # ISO YYYY-MM-DD
    # Sales tab
    taxable_sales: float
    non_taxable: float
    sales_tax: float
    # Receipts (operator-editable)
    bill_payment_charge: float
    phone_recargas: float
    boost_mobile: float
    money_transfer: float
    money_order: float
    money_order_fees: float
    check_cashing_fees: float
    return_check_hold_fees: float
    forward_balance: float
    # True when ``forward_balance`` is auto-carried from the previous
    # logged day (prior.outside_cash_drops + prior.safe_balance) and
    # the editor should render it read-only. False only on the very
    # first logged day, where the operator seeds the opening balance
    # by hand. See ``carry_forward_from`` + INVARIANTS.md.
    forward_balance_auto: bool
    from_bank: float
    rebates_commissions: float
    # Receipts (line-item derived)
    return_check_paid_back: float
    other_cash_in: float
    # Disbursements (operator-editable)
    cash_deposit: float
    safe_balance: float
    payroll_expense: float
    # Check payroll — line-item derived, NOT part of the daily
    # totals (feeds the monthly P&L only).
    payroll_check: float
    # Disbursements (line-item derived)
    cash_purchases: float
    cash_expense: float
    check_purchases: float
    check_expense: float
    outside_cash_drops: float
    checks_deposit: float
    other_cash_out: float
    # Other
    over_short: float
    locked: bool
    notes: str
    locked_at: str  # ISO datetime, or "" when unlocked
    # Derived
    total_receipts: float
    total_disbursements: float
    net: float


@dataclass
class PeriodSummary:
    """Roll-up for a date range. `rows` are individual reports; the
    summary fields are sums across them. Empty-period returns zeros
    + an empty list."""
    rows: list[DailyReportSummary]
    total_receipts: float
    total_disbursements: float
    net: float
    days_logged: int


def carry_forward_from(prior: DailyReport) -> float:
    """The forward balance a day inherits from the previous logged
    day = that day's cash left the store overnight: what was dropped
    to the safe / outside (``outside_cash_drops``) plus what stayed
    in the safe (``safe_balance``). This is the opening cash the next
    day starts with. Confirmed with the operator as the carry rule."""
    return float((prior.outside_cash_drops or 0) + (prior.safe_balance or 0))


def _summarize(
    r: DailyReport, *, forward_auto: float | None = None,
) -> DailyReportSummary:
    """Wire-shape one report. When ``forward_auto`` is not None the
    forward balance is auto-carried from the previous logged day —
    we override the stored column with the fresh carry value (so the
    editor reflects a prior-day edit even before this day is re-saved)
    and adjust receipts / net by the delta. ``forward_auto is None``
    means "first logged day" — the operator-seeded stored value
    stands and the field stays editable."""
    stored_forward = float(r.forward_balance or 0)
    forward = stored_forward if forward_auto is None else float(forward_auto)
    forward_delta = forward - stored_forward
    base_receipts = float(r.total_receipts or 0)
    total_receipts = base_receipts + forward_delta
    total_disbursements = float(r.total_disbursements or 0)
    return DailyReportSummary(
        id=int(r.id),
        store_id=int(r.store_id),
        report_date=r.report_date.isoformat() if r.report_date else "",
        taxable_sales=float(r.taxable_sales or 0),
        non_taxable=float(r.non_taxable or 0),
        sales_tax=float(r.sales_tax or 0),
        bill_payment_charge=float(r.bill_payment_charge or 0),
        phone_recargas=float(r.phone_recargas or 0),
        boost_mobile=float(r.boost_mobile or 0),
        money_transfer=float(r.money_transfer or 0),
        money_order=float(r.money_order or 0),
        money_order_fees=float(r.money_order_fees or 0),
        check_cashing_fees=float(r.check_cashing_fees or 0),
        return_check_hold_fees=float(r.return_check_hold_fees or 0),
        forward_balance=forward,
        forward_balance_auto=forward_auto is not None,
        from_bank=float(r.from_bank or 0),
        rebates_commissions=float(r.rebates_commissions or 0),
        return_check_paid_back=float(r.return_check_paid_back or 0),
        other_cash_in=float(r.other_cash_in or 0),
        cash_deposit=float(r.cash_deposit or 0),
        safe_balance=float(r.safe_balance or 0),
        payroll_expense=float(r.payroll_expense or 0),
        payroll_check=float(getattr(r, "payroll_check", 0) or 0),
        cash_purchases=float(r.cash_purchases or 0),
        cash_expense=float(r.cash_expense or 0),
        check_purchases=float(r.check_purchases or 0),
        check_expense=float(r.check_expense or 0),
        outside_cash_drops=float(r.outside_cash_drops or 0),
        checks_deposit=float(r.checks_deposit or 0),
        other_cash_out=float(r.other_cash_out or 0),
        # Over/Short is derived (see DailyReport.computed_over_short),
        # recomputed here from the carry-adjusted totals so the displayed
        # reconciliation tracks a prior-day edit before this day is
        # re-saved — same treatment as `net` above. Equals the stored
        # column except by the forward-carry delta.
        over_short=(
            total_disbursements
            - float(r.check_purchases or 0) - float(r.check_expense or 0)
            + float(r.safe_balance or 0)
            - total_receipts
        ),
        locked=r.locked_at is not None,
        notes=str(r.notes or ""),
        locked_at=r.locked_at.isoformat() if r.locked_at else "",
        total_receipts=total_receipts,
        total_disbursements=total_disbursements,
        net=total_receipts - total_disbursements,
    )


def _carry_only_summary(
    store_id: int, report_date: date, forward: float,
) -> DailyReportSummary:
    """A virtual, not-yet-saved day that carries only the forward
    balance from the previous logged day. Every other field is zero.
    Returned by ``summarize_report`` when the operator opens a fresh
    day (no row saved yet) that nonetheless has a prior day to carry
    from — so the forward-balance box shows the carried value
    read-only *before* the first save, instead of a blank editable
    field. ``id=0`` flags "not persisted"; the editor keys every
    write off (store, date), never the id, so this is safe."""
    return DailyReportSummary(
        id=0, store_id=store_id, report_date=report_date.isoformat(),
        taxable_sales=0.0, non_taxable=0.0, sales_tax=0.0,
        bill_payment_charge=0.0, phone_recargas=0.0, boost_mobile=0.0,
        money_transfer=0.0, money_order=0.0, money_order_fees=0.0,
        check_cashing_fees=0.0, return_check_hold_fees=0.0,
        forward_balance=forward, forward_balance_auto=True,
        from_bank=0.0, rebates_commissions=0.0,
        return_check_paid_back=0.0, other_cash_in=0.0,
        cash_deposit=0.0, safe_balance=0.0, payroll_expense=0.0,
        payroll_check=0.0,
        cash_purchases=0.0, cash_expense=0.0, check_purchases=0.0,
        check_expense=0.0, outside_cash_drops=0.0, checks_deposit=0.0,
        other_cash_out=0.0, over_short=0.0,
        locked=False, notes="", locked_at="",
        total_receipts=forward, total_disbursements=0.0, net=forward,
    )


def summarize_report(
    db: Session, store_id: int, report_date: date,
) -> DailyReportSummary | None:
    """Single-report summary by `(store, date)`.

    Forward balance is auto-carried from the most recent prior logged
    day whenever one exists — including on a **fresh, not-yet-saved
    day**: if no row exists here yet but a prior day does, we return a
    virtual carry-only summary so the forward-balance box shows the
    carried value read-only before the operator saves anything.

    Returns `None` only when the store has NO prior report at all —
    the genuine first day, where the operator seeds the opening
    balance by hand (``forward_balance_auto=False`` once saved)."""
    r = find_report_by_date(db, store_id, report_date)
    prior = find_prior_report(db, store_id, report_date)
    if r is None:
        if prior is None:
            return None
        return _carry_only_summary(
            store_id, report_date, carry_forward_from(prior),
        )
    forward_auto = carry_forward_from(prior) if prior is not None else None
    return _summarize(r, forward_auto=forward_auto)


def summarize_period(
    db: Session, store_ids: Iterable[int],
    d_from: date, d_to: date,
) -> PeriodSummary:
    """Date-range summary. Same row order as
    `list_reports_in_period`: report_date asc + id tie-break."""
    rows = list_reports_in_period(db, store_ids, d_from, d_to)
    summaries = [_summarize(r) for r in rows]
    total_receipts = sum(s.total_receipts for s in summaries)
    total_disbursements = sum(s.total_disbursements for s in summaries)
    return PeriodSummary(
        rows=summaries,
        total_receipts=total_receipts,
        total_disbursements=total_disbursements,
        net=total_receipts - total_disbursements,
        days_logged=len(summaries),
    )


# ── Write-side lifecycle ─────────────────────────────────────


def ensure_daily_report(
    db: Session, store_id: int, report_date: date,
) -> DailyReport:
    """Return the DailyReport for `(store, date)`, creating an empty
    one with all zero-default fields if it doesn't exist yet. Same
    contract as the legacy `_ensure_daily_report`. The caller is
    responsible for committing — we flush so the new row gets an id."""
    report = find_report_by_date(db, store_id, report_date)
    if report is None:
        report = DailyReport(store_id=store_id, report_date=report_date)
        db.add(report)
        db.flush()
    return report


# Editable totals on the daily report. Subset of the legacy
# `_DAILY_REPORT_FIELDS` constant in app.py — the SPA's first
# write-side cut intentionally limits to top-level totals; line
# items (drops, check deposits) and per-MT-company breakdowns
# are derived from their own tables and migrate in follow-up PRs.
# `over_short` is deliberately NOT here — it's a derived cash-drawer
# reconciliation, computed server-side (DailyReport.computed_over_short)
# and never typed. Sending it would 422 (the request schema forbids
# extras). See INVARIANTS.md → "Over/Short is derived".
EDITABLE_REPORT_FIELDS: tuple[str, ...] = (
    "taxable_sales", "non_taxable", "sales_tax",
    "bill_payment_charge", "phone_recargas", "boost_mobile",
    "money_order_fees",
    "check_cashing_fees", "return_check_hold_fees",
    "forward_balance", "rebates_commissions",
    "cash_deposit", "safe_balance",
)


class DailyReportLockedError(Exception):
    """Raised when a write touches a locked DailyReport. The
    SPA shows this as a 403 with a clear "unlock first" message
    — same UX as the legacy template's locked-banner."""


def update_daily_report(
    db: Session, *,
    store_id: int, report_date: date,
    fields: dict[str, float], notes: str = "",
) -> DailyReport:
    """Save the editable totals for one DailyReport.

    Auto-creates the row when it doesn't exist (matches the legacy
    `daily_report` route's POST behavior).

    Refuses to save when `locked_at` is set — raises
    `DailyReportLockedError`. Caller maps that to HTTP 403.

    Only fields in `EDITABLE_REPORT_FIELDS` are written; the body
    can carry only the subset the form actually edited.
    Line-item-derived fields (cash_purchases, cash_expense, etc.)
    are not in this set — they roll up from DailyLineItem rows
    and stay on the legacy /daily-book write path until that
    migration lands.

    Caller commits.
    """
    report = ensure_daily_report(db, store_id, report_date)
    if report.locked_at is not None:
        raise DailyReportLockedError(
            "Daily report is locked — unlock it before editing."
        )
    # Forward balance auto-carries from the previous logged day when
    # one exists — the operator can't override it (mirrors the auto
    # sales-tax field). We skip any client-sent forward_balance here
    # and force the carried value below, so a stale form can't clobber
    # it. Only the very first logged day (no prior report) honours the
    # operator-entered seed.
    prior = find_prior_report(db, store_id, report_date)
    for field in EDITABLE_REPORT_FIELDS:
        if field == "forward_balance" and prior is not None:
            continue
        if field in fields:
            setattr(report, field, float(fields[field] or 0))
    if prior is not None:
        report.forward_balance = carry_forward_from(prior)
    report.notes = notes or ""
    # Over/Short is derived, not typed — recompute it from the freshly
    # written fields so the stored column (read by the owner dashboards,
    # tax export, and daily-summary email) is always the correct
    # reconciliation.
    report.over_short = report.computed_over_short
    report.updated_at = utc_now()
    db.flush()
    return report


def lock_report(
    db: Session, store_id: int, report_date: date,
    locked_by_user_id: int | None = None,
) -> DailyReport:
    """Mark a daily report as locked. Idempotent — already-locked
    reports keep their original locked_at/locked_by; we don't bump
    updated_at in that case so re-clicking the lock button doesn't
    look like an edit. Auto-creates an empty DailyReport if missing
    so the user can lock an empty day on purpose."""
    report = ensure_daily_report(db, store_id, report_date)
    if report.locked_at is None:
        now = utc_now()
        report.locked_at = now
        report.locked_by = locked_by_user_id
        report.updated_at = now
        db.flush()
    return report


def unlock_report(
    db: Session, store_id: int, report_date: date,
) -> DailyReport | None:
    """Clear the lock on a daily report. Returns the unlocked row or
    None when no report exists for the date (no-op)."""
    report = find_report_by_date(db, store_id, report_date)
    if report is None or report.locked_at is None:
        return report
    setattr(report, "locked_at", None)
    setattr(report, "locked_by", None)
    setattr(report, "updated_at", utc_now())
    db.flush()
    return report
