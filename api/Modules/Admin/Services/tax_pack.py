"""Tax-pack ZIP builder.

One-button "download my year-end packet" for tax prep. Rolls a
calendar year of store data into a single ZIP containing:

  * ``transfers_<year>.csv``     — full ledger including
                                    canceled / rejected rows.
  * ``monthly_pl_<year>.csv``    — one row per month from the
                                    ``MonthlyFinancial`` table.
  * ``daily_summary_<year>.csv`` — one row per ``DailyReport``.
  * ``customers_<year>.csv``     — per-customer totals.
  * ``README.txt``               — plain-text key for the accountant.

Service-layer only; the HTTP wrapper lives in
``api/Modules/Admin/Controllers``.
"""
from __future__ import annotations

import io
import zipfile
from datetime import date

from sqlalchemy import func
from sqlalchemy.orm import Session

from api.Modules.Customers.Models import Customer
from api.Modules.DailyBook.Models import DailyReport
from api.Modules.Monthly.Models import MonthlyFinancial
from api.Modules.Tenancy.Models import Store, User
from api.Modules.Transfers.Models import Transfer
from api.Core.Clock import utc_now
from api.Core.Csv import build_csv


def _transfers_csv(db: Session, store_id: int, year: int) -> str:
    """Full transfer ledger for the year. Includes Canceled /
    Rejected so the accountant has the audit trail; the Status
    column lets them filter in Excel."""
    headers = [
        "Send Date", "Company", "Service Type", "Sender Name",
        "Sender Phone", "Recipient Name", "Country",
        "Send Amount", "Fee", "Federal Tax", "Total Collected",
        "Confirm Number", "Batch ID", "Status",
        "Employee", "Created By", "Internal Notes",
    ]
    rows = (
        db.query(Transfer)
          .filter(
              Transfer.store_id == store_id,
              Transfer.send_date >= date(year, 1, 1),
              Transfer.send_date <= date(year, 12, 31),
          )
          .order_by(Transfer.send_date, Transfer.id)
          .all()
    )
    user_ids = {t.created_by for t in rows if t.created_by}
    users = (
        {u.id: u for u in db.query(User).filter(User.id.in_(user_ids)).all()}
        if user_ids else {}
    )

    def _row(t: Transfer) -> list[object]:
        u = users.get(t.created_by) if t.created_by else None
        creator = (u.full_name or u.username) if u else ""
        phone = (
            (t.sender_phone_country or "") + (t.sender_phone or "")
        ).strip()
        total = (
            (t.send_amount or 0) + (t.fee or 0) + (t.federal_tax or 0)
        )
        return [
            t.send_date.isoformat() if t.send_date else "",
            t.company or "",
            t.service_type or "",
            t.sender_name or "",
            phone,
            t.recipient_name or "",
            t.country or "",
            f"{t.send_amount:.2f}" if t.send_amount is not None else "",
            f"{t.fee:.2f}" if t.fee is not None else "",
            f"{t.federal_tax:.2f}" if t.federal_tax is not None else "",
            f"{total:.2f}",
            t.confirm_number or "",
            t.batch_id or "",
            t.status or "",
            t.employee_name or "",
            creator,
            t.internal_notes or "",
        ]

    return build_csv(headers, (_row(t) for t in rows))


def _monthly_pl_csv(db: Session, store_id: int, year: int) -> str:
    """Per-month roll-up of MonthlyFinancial. Discovers columns
    dynamically so any future P&L line auto-appears in the export."""
    rows = {
        r.month: r for r in
        db.query(MonthlyFinancial)
          .filter_by(store_id=store_id, year=year)
          .all()
    }
    sample = next(iter(rows.values()), None)
    if sample is None:
        money_cols = ["taxable_sales", "non_taxable", "over_short"]
    else:
        money_cols = [
            c.name for c in MonthlyFinancial.__table__.columns
            if c.name not in (
                "id", "store_id", "year", "month",
                "notes", "updated_at",
            )
        ]
    headers = (
        ["Month"]
        + [c.replace("_", " ").title() for c in money_cols]
        + ["Net Income"]
    )

    def _row(m: int) -> list[object]:
        r = rows.get(m)
        if r:
            values = [getattr(r, c, 0.0) or 0.0 for c in money_cols]
            net = float(getattr(r, "net_income", 0.0) or 0.0)
        else:
            values = [0.0] * len(money_cols)
            net = 0.0
        return (
            [f"{year}-{m:02d}"]
            + [f"{v:.2f}" for v in values]
            + [f"{net:.2f}"]
        )

    return build_csv(headers, (_row(m) for m in range(1, 13)))


def _daily_summary_csv(db: Session, store_id: int, year: int) -> str:
    """One row per DailyReport. Receipts + Disbursements + over/short
    are the headline numbers an accountant cross-checks against the
    bank statement."""
    rows = (
        db.query(DailyReport)
          .filter(
              DailyReport.store_id == store_id,
              DailyReport.report_date >= date(year, 1, 1),
              DailyReport.report_date <= date(year, 12, 31),
          )
          .order_by(DailyReport.report_date)
          .all()
    )
    headers = [
        "Date", "Total Receipts", "Total Disbursements",
        "Over/Short", "Locked",
    ]

    def _row(r: DailyReport) -> list[object]:
        receipts  = float(getattr(r, "total_receipts", 0.0) or 0.0)
        disbursed = float(getattr(r, "total_disbursements", 0.0) or 0.0)
        os_       = float(getattr(r, "over_short", 0.0) or 0.0)
        locked    = "yes" if getattr(r, "locked_at", None) else "no"
        return [
            r.report_date.isoformat(),
            f"{receipts:.2f}", f"{disbursed:.2f}", f"{os_:.2f}",
            locked,
        ]

    return build_csv(headers, (_row(r) for r in rows))


def _customers_csv(db: Session, store_id: int, year: int) -> str:
    """Per-customer totals for the year — count, total sent, total
    fees. Useful as a starting point for 1099-MISC reporting.
    Walk-in transfers (no Customer link) are bucketed as
    ``(walk-in)``. Canceled / Rejected transfers are excluded."""
    from api.Modules.Owners.Services import OWNER_TRANSFER_EXCLUDED
    rows = (
        db.query(
            Transfer.customer_id,
            Transfer.sender_name,
            func.count(Transfer.id),
            func.coalesce(func.sum(Transfer.send_amount_cents), 0) / 100.0,
            func.coalesce(func.sum(Transfer.fee_cents), 0) / 100.0,
        )
        .filter(
            Transfer.store_id == store_id,
            Transfer.send_date >= date(year, 1, 1),
            Transfer.send_date <= date(year, 12, 31),
            Transfer.status.notin_(OWNER_TRANSFER_EXCLUDED),
        )
        .group_by(Transfer.customer_id, Transfer.sender_name)
        .order_by(func.sum(Transfer.send_amount_cents).desc())
        .all()
    )
    cust_ids = {cid for cid, *_ in rows if cid is not None}
    customers = (
        {c.id: c for c in
         db.query(Customer).filter(Customer.id.in_(cust_ids)).all()}
        if cust_ids else {}
    )
    headers = [
        "Customer", "Phone", "Address", "Count",
        "Total Sent", "Total Fees",
    ]

    def _row(group: tuple) -> list[object]:
        cid, sender_name, count, sent, fees = group
        if cid and cid in customers:
            c = customers[cid]
            name = c.full_name or sender_name or "(no name)"
            phone = (
                f"{c.phone_country}{c.phone_number}"
                if c.phone_number else ""
            )
            address = c.address or ""
        else:
            name = sender_name or "(walk-in)"
            phone = ""
            address = ""
        return [
            name, phone, address, int(count or 0),
            f"{float(sent or 0):.2f}", f"{float(fees or 0):.2f}",
        ]

    return build_csv(headers, (_row(g) for g in rows))


def _readme(store: Store, year: int) -> str:
    """Plain-text README explaining each file. Hand-written copy —
    operators hand the whole pack to their accountant, so the
    README is the only context the accountant has."""
    return (
        f"DineroBook Tax Export Pack\n"
        f"==========================\n"
        f"Store:  {store.name}\n"
        f"Year:   {year}\n"
        f"Generated: {utc_now().strftime('%Y-%m-%d %H:%M UTC')}\n"
        f"\n"
        f"Files in this archive:\n"
        f"\n"
        f"  transfers_{year}.csv\n"
        f"      Full transfer ledger for the calendar year. Includes\n"
        f"      Canceled / Rejected rows so you can verify nothing is\n"
        f"      missing — filter the Status column in Excel/Sheets to\n"
        f"      isolate revenue-bearing transfers.\n"
        f"\n"
        f"  monthly_pl_{year}.csv\n"
        f"      Month-by-month profit & loss roll-up matching the\n"
        f"      Monthly P&L page. Net Income column is income minus\n"
        f"      expenses for the month.\n"
        f"\n"
        f"  daily_summary_{year}.csv\n"
        f"      One row per closed daily book — receipts, disbursements,\n"
        f"      over/short. Cross-check against bank deposits.\n"
        f"\n"
        f"  customers_{year}.csv\n"
        f"      Per-customer totals (count, total sent, fees). Starting\n"
        f"      point for 1099-MISC if any single customer crossed the\n"
        f"      IRS reporting threshold for the year.\n"
        f"\n"
        f"All money values are USD. Send amounts are what the customer\n"
        f"handed over; fees are what the store retained; federal tax is\n"
        f"the portion that left with the ACH withdrawal (not store\n"
        f"revenue).\n"
        f"\n"
        f"Questions: support@dinerobook.com\n"
    )


def build_tax_pack_zip(db: Session, store: Store, year: int) -> bytes:
    """Assemble every CSV + README into an in-memory ZIP and return
    the bytes. Caller wraps in a Response with the right
    ``Content-Type`` + ``Content-Disposition`` headers."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(
            f"transfers_{year}.csv",
            _transfers_csv(db, store.id, year),
        )
        zf.writestr(
            f"monthly_pl_{year}.csv",
            _monthly_pl_csv(db, store.id, year),
        )
        zf.writestr(
            f"daily_summary_{year}.csv",
            _daily_summary_csv(db, store.id, year),
        )
        zf.writestr(
            f"customers_{year}.csv",
            _customers_csv(db, store.id, year),
        )
        zf.writestr("README.txt", _readme(store, year))
    return buf.getvalue()
