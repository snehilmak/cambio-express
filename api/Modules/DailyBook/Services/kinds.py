"""Daily-book line-item kinds.

The canonical registry of line-item kinds the daily P&L recognizes.
Each kind maps to:

  - the `DailyReport` column its rows roll up into (the `_recompute_
    line_items_total` Service writes the sum back here)
  - a singular operator-friendly label (used in flash messages /
    confirmations)
  - a plural / unit label (rendered in row counts on the report —
    "3 entries" vs. "2 drops" vs. "1 deposit")

Per CLAUDE.md, adding a new kind is:
  1. one entry in this dict
  2. one disclosure widget on the daily-report template
  3. removing the field from `_DAILY_REPORT_FIELDS` (so the column
     becomes derived rather than directly editable)

The `kind_or_404` helper raises a Flask abort when a request
references an unknown kind — used by the daily-report routes to
guard the `/daily-report/<date>/<kind>/...` URL family.
"""
from typing import Iterable


# kind → (daily_report_field, singular_label, plural_label_for_count)
LINE_ITEM_KINDS: dict[str, tuple[str, str, str]] = {
    "return_payback": ("return_check_paid_back", "return check payback", "entries"),
    "cash_purchase":  ("cash_purchases",         "cash purchase",        "entries"),
    "cash_expense":   ("cash_expense",           "cash expense",         "entries"),
    "check_purchase": ("check_purchases",        "check purchase",       "entries"),
    "check_expense":  ("check_expense",          "check expense",        "entries"),
    # Catch-all "other" buckets — a single day can have multiple
    # ad-hoc cash-ins (refunds, owner contributions) and cash-outs
    # (one-off payouts that don't fit Payroll or Drops). Backed by
    # the same `DailyLineItem` model + auto-derived total contract
    # as the rest of the kinds above.
    "other_cash_in":  ("other_cash_in",          "other cash in",        "entries"),
    "other_cash_out": ("other_cash_out",         "other cash out",       "entries"),
    # Cash pulled from the bank into the drawer. A store can make
    # multiple bank runs in a day, so this is a multi-entry kind like
    # drops — was a single operator-typed `from_bank` total before the
    # conversion; existing values were backfilled to one line item.
    "from_bank":      ("from_bank",               "cash from bank",       "entries"),
    # Money orders sold. Some operators enter one aggregate total for
    # the day, others log each money order separately — both work as
    # line items. Was a single operator-typed `money_order` total;
    # existing values were backfilled to one line item.
    "money_order":    ("money_order",              "money order",          "entries"),
    # Payroll paid out. Cash payroll moves real drawer cash so it
    # rolls into `payroll_expense` (a daily disbursement, as the
    # typed field always did). CHECK payroll deliberately does NOT
    # touch the daily book's numbers — `payroll_check` is excluded
    # from total_disbursements/over_short and exists only to feed
    # the monthly P&L's check-payroll line.
    "payroll_cash":   ("payroll_expense",          "cash payroll",         "entries"),
    "payroll_check":  ("payroll_check",            "check payroll",        "entries"),
    # Outside-cash drops (ATM drops, safe drops). Originally lived
    # in its own `DailyDrop` table + bespoke routes/IIFE —
    # collapsed into the generic kind system after the data
    # migration. The legacy `DailyDrop` table is preserved
    # (data not deleted) but the code path no longer references it.
    "drop":           ("outside_cash_drops",     "drop",                 "drops"),
    # Check deposits (morning/afternoon trips to the bank). Same
    # story as drops — was its own `CheckDeposit` table; now a
    # kind.
    "check_deposit":  ("checks_deposit",         "check deposit",        "deposits"),
}


def is_known_kind(kind: str) -> bool:
    """True if `kind` is a registered line-item kind."""
    return kind in LINE_ITEM_KINDS


def kind_or_404(kind: str) -> tuple[str, str, str]:
    """Return the registry tuple for ``kind``, or raise an
    ``HTTPException(404)`` when unknown. Used by the daily-report
    URL family to guard ``<kind>`` path segments."""
    if kind not in LINE_ITEM_KINDS:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=f"Unknown kind '{kind}'.")
    return LINE_ITEM_KINDS[kind]


def all_kinds() -> Iterable[str]:
    """Iterate the registered kind keys. Convenience for templates
    + scripts that need to enumerate."""
    return LINE_ITEM_KINDS.keys()


def field_for_kind(kind: str) -> str | None:
    """The `DailyReport` column name a kind rolls up into. None
    when the kind isn't in the registry."""
    entry = LINE_ITEM_KINDS.get(kind)
    return entry[0] if entry else None
