"""Commit a parsed Intermex daily report into the day's money-transfer
breakdown (``MoneyTransferSummary``).

Intermex daily-close reports carry only the financial rows (confirm
number, send amount, fee, federal tax, deposit balance) — **no sender /
recipient PII** — so they can't become individual ``Transfer`` rows.
What they CAN fill is the daily book's per-company money-transfer
breakdown: the active giros aggregate to the Intermex company row
(``amount = Σ send``, ``fees = Σ fee``, ``federal_tax = Σ federal_tax``),
which is exactly the surface the operator would otherwise hand-key on
the receipts tab.

Reconcile: we compare the report's aggregate against the transfers the
store already logged for that day (``summarize_transfers_for_day``), so
the operator can see whether the report matches their own entries.

Only the Intermex row is touched — every other company's manual
override is preserved (auto-only companies stay on their auto value).
Re-committing the same report is idempotent (it sets the Intermex row
to the same aggregate).
"""
from dataclasses import dataclass
from datetime import date

from sqlalchemy.orm import Session

from api.Modules.DailyBook.Services.mt_breakdown import (
    MTWriteRow,
    read_mt_breakdown,
    replace_mt_breakdown,
)
from api.Modules.ReportImport.Services.intermex import IntermexDailyReport

INTERMEX_COMPANY = "Intermex"
# Dollar-compare tolerance for the reconcile flag (half a cent).
_CENTS = 0.005


class ReportCommitError(ValueError):
    """Raised when a report can't be committed — no settled giros, or
    the giros don't reconcile so the totals are untrustworthy. The
    controller maps this to HTTP 422."""


@dataclass
class IntermexCommitResult:
    """Outcome of a commit, including the reconcile comparison against
    already-logged transfers."""
    company: str
    giros_committed: int
    amount: float                # Σ send of active giros
    fees: float                  # Σ fee
    federal_tax: float           # Σ federal_tax
    committed_total: float       # amount + fees + federal_tax (Intermex)
    grand_total: float           # new day MT grand total (all companies)
    logged_amount: float         # Intermex send total already in Transfer log
    logged_total: float          # Intermex send+fee+tax+comm already logged
    previous_saved_total: float  # Intermex saved MT-row total before commit
    matches_logged: bool         # report send total ≈ already-logged send total


def commit_intermex_to_mt_breakdown(
    db: Session, *, store_id: int, report_date: date,
    report: IntermexDailyReport, company: str = INTERMEX_COMPANY,
) -> IntermexCommitResult:
    """Aggregate the report's active giros into the ``company`` row of
    the day's MT breakdown, preserving every other company's saved
    override. Caller commits. Raises ``ReportCommitError`` (→422) when
    there's nothing safe to commit, or ``DailyReportLockedError``
    (→403) when the day is locked."""
    active = report.active_giros
    if not active:
        raise ReportCommitError(
            "No settled giros to commit — every row is cancelled or the "
            "report has no Giros section."
        )
    if not report.all_reconcile:
        raise ReportCommitError(
            "The Giros don't reconcile against the report's stated total "
            "— fix the source report before committing."
        )

    amount = round(sum(g.send_amount for g in active), 2)
    fees = round(sum(g.fee for g in active), 2)
    federal_tax = round(sum(g.federal_tax for g in active), 2)
    committed_total = round(amount + fees + federal_tax, 2)

    # Snapshot the current breakdown: reconcile numbers for the target
    # company + every OTHER company's saved override we must carry over
    # (replace_mt_breakdown is a bulk replace, so anything we don't
    # re-send is dropped back to its auto value).
    before = read_mt_breakdown(db, store_id, report_date)
    prev_saved_total = 0.0
    logged_amount = 0.0
    logged_total = 0.0
    write_rows: list[MTWriteRow] = []
    for row in before.rows:
        saved_total = round(
            row.saved_amount + row.saved_fees
            + row.saved_federal_tax + row.saved_commission, 2,
        )
        if row.company == company:
            prev_saved_total = saved_total
            logged_amount = round(row.auto_amount, 2)
            logged_total = round(
                row.auto_amount + row.auto_fees
                + row.auto_federal_tax + row.auto_commission, 2,
            )
            continue  # the target row is set from the report below
        # Preserve other companies' manual overrides. Auto-only rows
        # (zero saved) are left out so they keep falling back to auto.
        if saved_total > 0:
            write_rows.append(MTWriteRow(
                company=row.company,
                amount=row.saved_amount, fees=row.saved_fees,
                federal_tax=row.saved_federal_tax,
                commission=row.saved_commission,
            ))

    write_rows.append(MTWriteRow(
        company=company, amount=amount, fees=fees,
        federal_tax=federal_tax, commission=0.0,
    ))

    grand_total = replace_mt_breakdown(
        db, store_id=store_id, report_date=report_date, rows=write_rows,
    )

    return IntermexCommitResult(
        company=company, giros_committed=len(active),
        amount=amount, fees=fees, federal_tax=federal_tax,
        committed_total=committed_total,
        grand_total=round(float(grand_total), 2),
        logged_amount=logged_amount, logged_total=logged_total,
        previous_saved_total=prev_saved_total,
        matches_logged=abs(amount - logged_amount) < _CENTS,
    )
