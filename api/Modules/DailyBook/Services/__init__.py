"""DailyBook — Services. Composes the Repository helpers into the
read-side flows for the daily P&L view + monthly roll-up, plus the
write-side lifecycle (lock / unlock) and line-item helpers.
"""
from api.Modules.DailyBook.Services.kinds import (
    LINE_ITEM_KINDS,
    all_kinds,
    field_for_kind,
    is_known_kind,
    kind_or_404,
)
from api.Modules.DailyBook.Services.line_items import (
    LineItemValidationError,
    add_line_item,
    delete_line_item,
    parse_amount,
    parse_at_time,
    recompute_line_items_total,
)
from api.Modules.DailyBook.Services.locks import (
    is_locked as is_daily_report_locked,
)
from api.Modules.DailyBook.Services.reports import (
    DailyReportLockedError,
    DailyReportSummary,
    EDITABLE_REPORT_FIELDS,
    PeriodSummary,
    ensure_daily_report,
    lock_report,
    summarize_period,
    summarize_report,
    unlock_report,
    update_daily_report,
)

__all__ = [
    "DailyReportLockedError",
    "DailyReportSummary",
    "EDITABLE_REPORT_FIELDS",
    "LINE_ITEM_KINDS",
    "LineItemValidationError",
    "PeriodSummary",
    "add_line_item",
    "all_kinds",
    "delete_line_item",
    "ensure_daily_report",
    "field_for_kind",
    "is_daily_report_locked",
    "is_known_kind",
    "kind_or_404",
    "lock_report",
    "parse_amount",
    "parse_at_time",
    "recompute_line_items_total",
    "summarize_period",
    "summarize_report",
    "unlock_report",
    "update_daily_report",
]
